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

"""PR-merge feature-reconcile dispatcher.

Called inline from the per-(org, repo) Redis-stream consumer
(:mod:`app.services.pr_merge_worker`) whenever a delivery is dequeued.
The dispatcher performs a cluster-scoped early-skip check before
deciding how to reconcile:

1. Load the WebhookLog row by ``delivery_id`` (replay payload lives
   there, not in the Redis message — Redis is for routing, Postgres
   is for state).
2. Fetch the PR's changed file paths from the GitHub API.
3. Backfill ``cluster_cache`` at the merge head SHA (the merge commit
   is brand new — no prior scan has populated it). Failure here falls
   through to the cache-miss branch downstream.
4. Compare cached cluster sets between the merge-base SHA and the
   merge-head SHA. Identify the *affected* clusters — newly present,
   newly absent, or whose member files intersect the PR's changed paths.
5. Branch:

   * ``len(affected) == 0`` → log and return. No LLM cost.
   * ``len(affected) <= NARROW_CAP`` → call
     :func:`run_narrow_synthesis` **inline** (same worker, no separate
     job). Phase-4 used a follow-up ``JOB_PR_NARROW_SYNTHESIS`` here;
     that job-handoff was the source of the lock-handoff race that
     Phase 5 eliminates.
   * ``len(affected) > NARROW_CAP`` → trigger a regular full scan.

The consumer task owns the WebhookLog lifecycle around this call
(``running → done`` / ``failed``). The dispatcher itself raises on
any unrecoverable failure; recoverable per-PR no-ops return silently.
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
from app.repositories.webhook_log import WebhookLogRepository
from app.services.github_app_auth import get_installation_token
from app.services.github_client import GitHubClient
from app.services.scan.cluster_index import index_and_cache
from app.services.scan.pr_narrow_synthesis import (
    NarrowSynthesisParams,
    run_narrow_synthesis,
)
from app.services.scan.runner import ScanAlreadyActiveError, start_scan

logger = structlog.get_logger(__name__)

# Cap on the number of affected clusters that go through the narrow
# synthesis path. Above this, fall back to today's full-repo scan path —
# at that point the prompt savings stop justifying a second LLM run vs.
# letting the standard pipeline's stage cache shortcut what it can.
NARROW_CAP = 10


class PrMergeDeliveryMissingError(RuntimeError):
    """Raised when the consumer hands us a delivery_id with no row.

    Recoverable: the consumer marks the row failed via its delivery_id
    and ACKs the stream message. The Postgres row may be missing only
    if it was hand-deleted by an operator (in which case the FAILED
    branch silently no-ops). Surfacing it as a typed exception keeps
    the worker's error log specific.
    """


async def handle_pr_merge_delivery(delivery_id: str) -> None:
    """Top-level entry point for one PR-merge delivery.

    Loads the replay row, runs the dispatcher, calls the narrow
    synthesis inline when applicable, and triggers a full scan
    otherwise. Raises on irrecoverable failures so the worker can
    flip the row to ``failed``.
    """
    async with AsyncSessionLocal() as db:
        row = await WebhookLogRepository(db).find_by_delivery_id(delivery_id)
    if row is None:
        raise PrMergeDeliveryMissingError(
            f"webhook_logs row not found for delivery_id={delivery_id}"
        )
    if row.repo_id is None or not row.payload:
        # FK SET NULL on repo deletion, or row was inserted in audit-
        # only mode by mistake — either way there is no work to do.
        logger.warning(
            "pr_merge_delivery_unreplayable",
            delivery_id=delivery_id,
            has_repo_id=row.repo_id is not None,
            has_payload=row.payload is not None,
        )
        return

    payload = row.payload
    try:
        pr_number = int(payload["pr_number"])
        base_sha = str(payload["base_sha"])
        head_sha = str(payload["head_sha"])
        full_name = str(payload.get("full_name") or "")
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(
            f"replay payload missing PR-merge fields for delivery_id={delivery_id}: {exc}"
        ) from exc

    narrow_params = await _run_dispatch(
        org_id=row.org_id,
        repo_id=row.repo_id,
        pr_number=pr_number,
        base_sha=base_sha,
        head_sha=head_sha,
        full_name=full_name,
    )
    if narrow_params is None:
        return

    # Narrow path: call inline. The consumer task is the per-(org, repo)
    # serialization boundary, so there is no lock to defer on and no
    # race with the dispatcher's prior work.
    outcome = await run_narrow_synthesis(narrow_params)
    if not outcome.succeeded:
        # The Claude run itself failed (cost-bearing branch). The
        # delivery row gets flipped to ``failed`` so operators can
        # inspect; the worker re-raises into its caller to drive that.
        raise RuntimeError(outcome.error or "narrow synthesis failed")
    # Narrow synth succeeded — the cluster_cache rows at head_sha and
    # the affected features are now coherent. Stamp head_sha on the
    # tracked repo so downstream readers (index builder, next
    # delivery's base_sha lookup) line up with what we just wrote.
    await _advance_tracked_head_sha(org_id=row.org_id, repo_id=row.repo_id, head_sha=head_sha)
    logger.info(
        "pr_merge_delivery_narrow_done",
        delivery_id=delivery_id,
        event_type=row.event_type,
        repo_id=str(row.repo_id),
        branch=outcome.branch,
        inserted=outcome.inserted,
        updated=outcome.updated,
        revived=outcome.revived,
        inactivated=outcome.inactivated,
    )


async def _run_dispatch(
    *,
    org_id: uuid.UUID,
    repo_id: uuid.UUID,
    pr_number: int,
    base_sha: str,
    head_sha: str,
    full_name: str,
) -> NarrowSynthesisParams | None:
    """Run the cluster-diff dispatch logic.

    Returns:
        :class:`NarrowSynthesisParams` when the narrow path is taken
        (caller calls :func:`run_narrow_synthesis` inline). ``None``
        for every terminal branch (cache miss → full scan, no affected
        clusters, repo/org missing) — those paths complete the work
        themselves without a follow-up.
    """
    async with AsyncSessionLocal() as db:
        repo, org = await _load_repo_and_org(db, org_id=org_id, repo_id=repo_id)
        if repo is None or org is None:
            logger.warning(
                "pr_merge_update_repo_or_org_missing",
                org_id=str(org_id),
                repo_id=str(repo_id),
            )
            return None

        changed_paths = await _fetch_changed_paths(org, full_name, pr_number)

        # Backfill cluster_cache for the merge SHA. The merge commit
        # is brand new — no scan has run against it — so without
        # this pre-step ``head_rows`` in ``_find_affected_clusters``
        # is empty and the narrow path is structurally unreachable.
        # The helper runs only the indexer (no LLM, no synthesis);
        # any failure falls through to the existing cache-miss
        # branch below, which still triggers a full scan.
        await _backfill_cluster_cache(
            org_id=org_id,
            repo_id=repo_id,
            repo_path=repo.path,
            head_sha=head_sha,
        )

        affected_result = await _find_affected_clusters(
            db,
            org_id=org_id,
            repo_id=repo_id,
            base_sha=base_sha,
            head_sha=head_sha,
            changed_paths=changed_paths,
            tracked_head_sha=repo.head_sha,
        )

    if affected_result is None:
        logger.info(
            "pr_merge_update_cache_miss_full_scan",
            repo_id=str(repo_id),
            base_sha=base_sha[:8],
            head_sha=head_sha[:8],
        )
        await _trigger_repo_scan(org_id=org_id, repo_id=repo_id, reason="cache_miss")
        return None

    affected, effective_base_sha = affected_result
    if not affected:
        # No semantic change in the code graph at head_sha. Still advance
        # tracked_repositories.head_sha so the BACKEND-route index
        # builder + future deliveries' base_sha fallback see the merged
        # commit as the new baseline — otherwise every subsequent PR's
        # diff would compare against an ever-older SHA and the
        # cache-miss branch fires unnecessarily.
        await _advance_tracked_head_sha(org_id=org_id, repo_id=repo_id, head_sha=head_sha)
        logger.info(
            "pr_merge_update_no_affected_clusters",
            repo_id=str(repo_id),
            pr_number=pr_number,
            changed_files=len(changed_paths),
        )
        return None

    logger.info(
        "pr_merge_update_clusters_affected",
        repo_id=str(repo_id),
        pr_number=pr_number,
        affected_count=len(affected),
        narrow_cap=NARROW_CAP,
    )
    if len(affected) <= NARROW_CAP:
        return NarrowSynthesisParams(
            org_id=org_id,
            repo_id=repo_id,
            pr_number=pr_number,
            base_sha=effective_base_sha,
            head_sha=head_sha,
            full_name=full_name,
            # Signatures (not cluster_ids) — cluster_ids are unstable
            # across SHAs because the indexer renumbers them when set
            # membership changes; signatures are SHA-256 of cluster
            # member node-IDs, stable for same content.
            affected_signatures=sorted(affected),
        )
    await _trigger_repo_scan(
        org_id=org_id,
        repo_id=repo_id,
        reason=f"{len(affected)} clusters affected (above narrow cap {NARROW_CAP})",
    )
    return None


async def _backfill_cluster_cache(
    *,
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
    tracked_head_sha: str | None = None,
) -> tuple[set[str], str] | None:
    """Cluster-level diff. Returns ``(affected_signatures, effective_base_sha)`` or ``None``.

    Algorithm:
      * Look up cluster_cache rows for the PR's ``base_sha``. If empty
        (most likely cause: main moved between the last scan and this
        merge via PRs whose webhooks pre-dated cache backfill), fall
        back to ``tracked_head_sha`` (the repo's last-scanned SHA the
        baseline scan always populates). The returned
        ``effective_base_sha`` tells the caller which SHA the diff was
        actually computed against, so the narrow handler can fetch
        removed-cluster signatures from the same SHA.
      * ``head_sha`` rows must exist (the backfill above writes them
        immediately before this call). If they're missing, return
        ``None`` and the caller falls back to a full scan.
      * ``added``: signature present at head, absent at base.
      * ``removed``: signature present at base, absent at head — the
        cluster was deleted by this PR. Surfacing these is what lets
        the narrow path soft-delete the matching feature with a SHA
        stamp instead of leaving an orphan active row.
      * ``modified``: surviving signatures whose member files
        intersect ``changed_paths``.
      * Return ``(added ∪ modified ∪ removed, effective_base_sha)``.
    """
    cache = ClusterCacheRepository(db, org_id=org_id)
    base_rows = await cache.list_for_repo_sha(repo_id=repo_id, head_sha=base_sha)
    effective_base_sha = base_sha
    if not base_rows and tracked_head_sha and tracked_head_sha != base_sha:
        fallback_rows = await cache.list_for_repo_sha(repo_id=repo_id, head_sha=tracked_head_sha)
        if fallback_rows:
            base_rows = fallback_rows
            effective_base_sha = tracked_head_sha
            logger.info(
                "pr_merge_update_base_sha_fallback",
                repo_id=str(repo_id),
                pr_base_sha=base_sha[:8],
                fallback_sha=tracked_head_sha[:8],
            )

    head_rows = await cache.list_for_repo_sha(repo_id=repo_id, head_sha=head_sha)
    if not base_rows or not head_rows:
        return None

    # NOTE: identify affected clusters by SIGNATURE, not ``cluster_id``.
    # The indexer reassigns numeric cluster_ids (c0, c1, …) when the set
    # of clusters changes — e.g., deleting one cluster shifts every
    # later cluster's id by one. ``cluster_id`` is therefore an
    # unstable identity across SHAs. The cluster's structural
    # ``signature`` (SHA-256 of its member node-IDs) IS stable: same
    # cluster contents → same signature regardless of which numeric
    # slot the indexer assigned it.
    base_sigs = {row.signature for row in base_rows if row.signature}
    head_sigs = {row.signature for row in head_rows if row.signature}

    added = head_sigs - base_sigs
    removed = base_sigs - head_sigs

    modified: set[str] = set()
    for row in head_rows:
        if not row.signature or row.signature not in base_sigs:
            continue
        files = set(row.files or [])
        if files & changed_paths:
            modified.add(row.signature)

    return (added | modified | removed, effective_base_sha)


async def _trigger_repo_scan(
    *,
    org_id: uuid.UUID,
    repo_id: uuid.UUID,
    reason: str,
) -> None:
    """Enqueue a regular scan, swallowing the already-active branch.

    The full-scan fallback runs independently of the per-delivery
    lifecycle: ``start_scan`` schedules its own pipeline and reports
    its own status, so the WebhookLog row reaches ``done`` once we
    return from here.
    """
    try:
        scan_id = await start_scan(org_id=org_id, repo_ids=[repo_id])
    except ScanAlreadyActiveError as exc:
        logger.info(
            "pr_merge_update_scan_already_active",
            org_id=str(org_id),
            existing_scan_id=str(exc.scan_id),
            existing_status=exc.status,
        )
        return
    logger.info(
        "pr_merge_update_scan_triggered",
        org_id=str(org_id),
        repo_id=str(repo_id),
        scan_id=str(scan_id),
        reason=reason,
    )


async def _advance_tracked_head_sha(
    *,
    org_id: uuid.UUID,
    repo_id: uuid.UUID,
    head_sha: str,
) -> None:
    """Stamp ``tracked_repositories.head_sha`` after a successful delivery.

    Called from the two delivery success terminals (no-affected-clusters
    and narrow-synth-succeeded) so PR-merge webhooks AND operator
    rescans converge ``head_sha`` onto the latest merged commit instead
    of leaving it pinned at the last full-scan SHA. Without this, every
    subsequent delivery's ``base_sha`` fallback compares against an
    increasingly stale SHA and the cache-miss branch fires unnecessarily.

    The cache-miss / over-cap branches DON'T call this — they kick off a
    full scan via :func:`_trigger_repo_scan` which has its own
    ``persist_results`` stage that updates ``head_sha``.

    Underlying :meth:`TrackedRepoRepository.advance_head_sha` is a no-op
    when ``head_sha`` is unchanged, so this is safe to call on every
    delivery (concurrent merges at the same SHA don't churn the
    timestamp).
    """
    async with AsyncSessionLocal() as db:
        await TrackedRepoRepository(db, org_id=org_id).advance_head_sha(repo_id, head_sha)
        await db.commit()
