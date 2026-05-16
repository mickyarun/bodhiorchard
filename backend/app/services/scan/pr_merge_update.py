# Copyright 2025-2026 Arun Rajkumar
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""PR-merge feature-reconcile job.

Triggered from the GitHub webhook handler when a PR is merged. The job
performs a cluster-scoped early-skip check before delegating to the
regular scan pipeline:

1. Fetch the PR's changed file paths from the GitHub API.
2. Compare cached cluster sets between the merge-base SHA and the
   merge-head SHA (``cluster_cache``). Identify the *affected* clusters
   — those that are newly present, newly absent, or whose member files
   intersect the PR's changed paths.
3. If no clusters are affected (very common: PRs touching only
   ``README.md`` / configs / tests fall here), log the skip and return.
   No LLM cost is incurred.
4. Otherwise dispatch the reconcile work based on how many clusters
   were affected:

   * ``len(affected) <= NARROW_CAP`` → enqueue a ``JOB_PR_NARROW_SYNTHESIS``
     job. The narrow handler runs Claude over those clusters only and
     reconciles with a signature-scoped ``candidate_filter`` so out-of-
     scope features are immune from soft-delete.
   * ``len(affected) > NARROW_CAP`` → enqueue a regular scan via
     :func:`start_scan`. The scan pipeline is SHA-gated, so unchanged
     stages are reused; the synthesise stage runs LLM only against
     the affected clusters' communities and the reconciler applies
     incremental CRUD as designed.

Concurrency: ``start_scan`` raises :class:`ScanAlreadyActiveError`
when an org-level scan is in flight. That's an expected branch — the
in-flight scan will pick up the merged changes, so we log and return
without enqueuing a duplicate.

Failure handling: the job worker catches all exceptions from this
handler and reports them via ``update_job(state=FAILED)``. The dedup
row in ``webhook_logs`` rolls back with the dispatching transaction so
GitHub's retry will re-attempt cleanly.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

import structlog

from app.database import AsyncSessionLocal
from app.models.organization import Organization
from app.models.tracked_repository import TrackedRepository
from app.repositories.cluster_cache import ClusterCacheRepository
from app.repositories.organization import OrganizationRepository
from app.repositories.tracked_repository import TrackedRepoRepository
from app.schemas.jobs import JobState
from app.services.github_app_auth import get_installation_token
from app.services.github_client import GitHubClient
from app.services.job_queue import JOB_PR_NARROW_SYNTHESIS, create_job, update_job
from app.services.scan.cluster_index import index_and_cache
from app.services.scan.runner import ScanAlreadyActiveError, start_scan

logger = structlog.get_logger(__name__)

# Cap on the number of affected clusters that go through the narrow
# synthesis job. Above this, fall back to today's full-repo scan path —
# at that point the prompt savings stop justifying a second LLM run vs.
# letting the standard pipeline's stage cache shortcut what it can.
NARROW_CAP = 10


async def handle_pr_merge_update(job_id: str, payload: dict[str, Any]) -> None:
    """Worker entry point for ``pr_merge_update`` jobs.

    Payload shape::

        {
            "org_id":    "<uuid>",
            "repo_id":   "<uuid>",
            "pr_number": int,
            "base_sha":  "<sha>",
            "head_sha":  "<sha>",
            "full_name": "<owner/repo>",
        }
    """
    try:
        org_id = uuid.UUID(payload["org_id"])
        repo_id = uuid.UUID(payload["repo_id"])
        pr_number = int(payload["pr_number"])
        base_sha = str(payload["base_sha"])
        head_sha = str(payload["head_sha"])
        full_name = str(payload["full_name"])
    except (KeyError, TypeError, ValueError) as exc:
        logger.error("pr_merge_update_bad_payload", job_id=job_id, payload=payload)
        update_job(job_id, state=JobState.FAILED, error=f"bad payload: {exc}")
        return

    update_job(job_id, state=JobState.RUNNING, status_message="Loading repo…")

    try:
        async with AsyncSessionLocal() as db:
            repo, org = await _load_repo_and_org(db, org_id=org_id, repo_id=repo_id)
            if repo is None or org is None:
                logger.warning(
                    "pr_merge_update_repo_or_org_missing",
                    org_id=str(org_id),
                    repo_id=str(repo_id),
                )
                update_job(job_id, state=JobState.COMPLETED, status_message="repo not tracked")
                return

            changed_paths = await _fetch_changed_paths(org, full_name, pr_number)
            update_job(job_id, status_message=f"PR touched {len(changed_paths)} files")

            # Backfill cluster_cache for the merge SHA. The merge commit
            # is brand new — no scan has run against it — so without
            # this pre-step ``head_rows`` in ``_find_affected_clusters``
            # is empty and the narrow path is structurally unreachable.
            # The helper runs only the indexer (no LLM, no synthesis);
            # any failure falls through to the existing cache-miss
            # branch below, which still triggers a full scan.
            await _backfill_cluster_cache(
                job_id=job_id,
                org_id=org_id,
                repo_id=repo_id,
                repo_path=repo.path,
                head_sha=head_sha,
            )

            affected = await _find_affected_clusters(
                db,
                org_id=org_id,
                repo_id=repo_id,
                base_sha=base_sha,
                head_sha=head_sha,
                changed_paths=changed_paths,
            )

        if affected is None:
            # cluster_cache miss for at least one of the SHAs — fall
            # through to a full scan rather than no-op so we don't leak
            # a real change.
            logger.info(
                "pr_merge_update_cache_miss_full_scan",
                repo_id=str(repo_id),
                base_sha=base_sha[:8],
                head_sha=head_sha[:8],
            )
            await _trigger_repo_scan(job_id, org_id=org_id, repo_id=repo_id, reason="cache_miss")
            return

        if not affected:
            logger.info(
                "pr_merge_update_no_affected_clusters",
                repo_id=str(repo_id),
                pr_number=pr_number,
                changed_files=len(changed_paths),
            )
            update_job(
                job_id,
                state=JobState.COMPLETED,
                status_message=f"No clusters affected by {len(changed_paths)} changed files",
            )
            return

        logger.info(
            "pr_merge_update_clusters_affected",
            repo_id=str(repo_id),
            pr_number=pr_number,
            affected_count=len(affected),
            narrow_cap=NARROW_CAP,
        )
        if len(affected) <= NARROW_CAP:
            _enqueue_narrow_synthesis(
                job_id,
                org_id=org_id,
                repo_id=repo_id,
                pr_number=pr_number,
                base_sha=base_sha,
                head_sha=head_sha,
                full_name=full_name,
                affected=affected,
            )
            return
        await _trigger_repo_scan(
            job_id,
            org_id=org_id,
            repo_id=repo_id,
            reason=f"{len(affected)} clusters affected (above narrow cap {NARROW_CAP})",
        )
    except Exception as exc:
        logger.exception("pr_merge_update_failed", job_id=job_id, repo_id=str(repo_id))
        update_job(job_id, state=JobState.FAILED, error=str(exc))


def _enqueue_narrow_synthesis(
    job_id: str,
    *,
    org_id: uuid.UUID,
    repo_id: uuid.UUID,
    pr_number: int,
    base_sha: str,
    head_sha: str,
    full_name: str,
    affected: set[str],
) -> None:
    """Enqueue the narrow synthesis job and mark this dispatcher job complete.

    If ``create_job`` raises, the exception propagates to the parent
    ``try``/``except`` in :func:`handle_pr_merge_update` and surfaces
    as ``state=FAILED`` — correct because the child was never queued.

    The trailing ``update_job(COMPLETED)`` is best-effort: the narrow
    child is already queued by then, so a failure to flip the
    dispatcher row's status only costs us telemetry, not correctness.
    Raising here would mask the success and trigger the outer FAILED
    path even though the work is in flight.
    """
    create_job(
        JOB_PR_NARROW_SYNTHESIS,
        payload={
            "org_id": str(org_id),
            "repo_id": str(repo_id),
            "pr_number": pr_number,
            "base_sha": base_sha,
            "head_sha": head_sha,
            "full_name": full_name,
            "affected_cluster_ids": sorted(affected),
        },
        user_id=None,
    )
    try:
        update_job(
            job_id,
            state=JobState.COMPLETED,
            status_message=f"Enqueued narrow synth for {len(affected)} cluster(s)",
        )
    except Exception:  # noqa: BLE001 — telemetry-only, not correctness
        logger.warning(
            "pr_merge_update_dispatcher_complete_log_failed",
            job_id=job_id,
            repo_id=str(repo_id),
            exc_info=True,
        )


async def _backfill_cluster_cache(
    *,
    job_id: str,
    org_id: uuid.UUID,
    repo_id: uuid.UUID,
    repo_path: str | None,
    head_sha: str,
) -> None:
    """Run the indexer at ``head_sha`` and write ``cluster_cache`` rows.

    Pre-step for the narrow path: without it, ``_find_affected_clusters``
    hits the cache-miss branch on every real-world PR merge (the merge
    commit has no prior cache rows). Any failure is swallowed and
    logged — the cache-miss branch downstream still triggers a full
    scan, so the only cost of a failed backfill is one extra full
    scan instead of a narrow one.
    """
    if not repo_path:
        logger.info(
            "pr_merge_update_backfill_skipped_no_path",
            repo_id=str(repo_id),
            head_sha=head_sha[:8],
        )
        return
    t0 = time.perf_counter()
    try:
        rows_written = await index_and_cache(
            org_id=org_id,
            repo_id=repo_id,
            repo_path=repo_path,
            head_sha=head_sha,
        )
    except Exception:
        logger.exception(
            "pr_merge_update_backfill_failed",
            job_id=job_id,
            repo_id=str(repo_id),
            head_sha=head_sha[:8],
        )
        return
    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    if rows_written == 0:
        # Indexer ran without crashing but produced zero rows — repo has
        # no source files, or the indexer's file collector filtered
        # everything out. ``_find_affected_clusters`` will still hit the
        # cache-miss branch downstream, so this surfaces the "ran but
        # empty" case at WARN so it's distinguishable from a real crash.
        logger.warning(
            "pr_merge_update_backfill_zero_rows",
            repo_id=str(repo_id),
            head_sha=head_sha[:8],
            elapsed_ms=elapsed_ms,
        )
        return
    logger.info(
        "pr_merge_update_backfill_done",
        repo_id=str(repo_id),
        head_sha=head_sha[:8],
        rows_written=rows_written,
        elapsed_ms=elapsed_ms,
    )


async def _load_repo_and_org(
    db: Any,
    *,
    org_id: uuid.UUID,
    repo_id: uuid.UUID,
) -> tuple[TrackedRepository | None, Organization | None]:
    """Resolve both records, returning ``(None, None)`` on any miss."""
    org = await OrganizationRepository(db).get_by_id(org_id)
    if org is None:
        return None, None
    repo = await TrackedRepoRepository(db, org_id=org_id).get_by_id(repo_id)
    if repo is None:
        return None, org
    return repo, org


async def _fetch_changed_paths(
    org: Organization,
    full_name: str,
    pr_number: int,
) -> set[str]:
    """Pull the PR's changed file list from GitHub. Empty set on auth miss."""
    token = await get_installation_token(org)
    if not token:
        logger.warning("pr_merge_update_no_install_token", org_id=str(org.id))
        return set()
    client = GitHubClient(token)
    files = await client.list_pr_files(full_name, pr_number)
    return set(files)


async def _find_affected_clusters(
    db: Any,
    *,
    org_id: uuid.UUID,
    repo_id: uuid.UUID,
    base_sha: str,
    head_sha: str,
    changed_paths: set[str],
) -> set[str] | None:
    """Cluster-level diff. Returns affected ``cluster_id`` set or ``None`` on cache miss.

    Algorithm:
      * Load the cached cluster lists for both SHAs.
      * If either is missing entirely → return ``None`` (caller falls
        back to a full scan).
      * ``added``: signature present at head, absent at base.
      * ``removed``: signature present at base, absent at head — the
        cluster was deleted by this PR (e.g. an entire module
        directory removed). Surfacing these is what lets the narrow
        path's reconciler soft-delete the matching feature with a
        commit-SHA stamp instead of leaving an orphan active row.
      * ``modified``: surviving signatures whose member files
        intersect ``changed_paths`` — the cluster's structure stayed
        the same but at least one of its files was touched.
      * Return added ∪ modified ∪ removed.
    """
    cache = ClusterCacheRepository(db, org_id=org_id)
    base_rows = await cache.list_for_repo_sha(repo_id=repo_id, head_sha=base_sha)
    head_rows = await cache.list_for_repo_sha(repo_id=repo_id, head_sha=head_sha)
    if not base_rows or not head_rows:
        return None

    base_sigs = {row.signature: row.cluster_id for row in base_rows if row.signature}
    head_sigs = {row.signature: row.cluster_id for row in head_rows if row.signature}

    added = {cluster_id for sig, cluster_id in head_sigs.items() if sig not in base_sigs}
    removed = {cluster_id for sig, cluster_id in base_sigs.items() if sig not in head_sigs}

    modified: set[str] = set()
    for row in head_rows:
        if not row.signature or row.signature not in base_sigs:
            continue
        files = set(row.files or [])
        if files & changed_paths:
            modified.add(row.cluster_id)

    return added | modified | removed


async def _trigger_repo_scan(
    job_id: str,
    *,
    org_id: uuid.UUID,
    repo_id: uuid.UUID,
    reason: str,
) -> None:
    """Enqueue a regular scan, swallowing the already-active branch."""
    try:
        scan_id = await start_scan(org_id=org_id, repo_ids=[repo_id])
    except ScanAlreadyActiveError as exc:
        logger.info(
            "pr_merge_update_scan_already_active",
            org_id=str(org_id),
            existing_scan_id=str(exc.scan_id),
            existing_status=exc.status,
        )
        update_job(
            job_id,
            state=JobState.COMPLETED,
            status_message=f"Scan already active ({exc.status}); re-merge picked up by it",
        )
        return
    update_job(
        job_id,
        state=JobState.COMPLETED,
        status_message=f"Triggered scan {scan_id} ({reason})",
    )
