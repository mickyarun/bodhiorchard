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

"""Index a repo + persist cluster_cache / repo_graph_cache rows for a SHA.

Two callers share this module:

* ``services/scan/stages/ingest.py`` — Stage 0 of the full scan
  pipeline. Calls :func:`persist_index_result` directly because it
  already runs the indexer itself (with all its scan-context plumbing —
  skip predicates, progress logging, etc.).
* ``services/scan/pr_merge_update.py`` — the PR-merge dispatcher.
  Calls :func:`index_and_cache` to ensure ``cluster_cache`` rows exist
  for the merge SHA *before* the dispatcher computes affected clusters.
  Without this pre-step, ``_find_affected_clusters`` returns ``None``
  on every real-world PR merge (the merge commit is brand new and has
  no prior cache rows), so the narrow-synthesis path is structurally
  unreachable.

Both writes are idempotent — ``ClusterCacheRepository.replace_for_repo_sha``
uses ``INSERT … ON CONFLICT DO UPDATE`` keyed on
``(org_id, repo_id, head_sha, cluster_id)``, so concurrent runs at the
same SHA converge on last-write-wins without corruption.
"""

from __future__ import annotations

import uuid

import structlog

from app.repositories.cluster_cache import ClusterCacheRepository
from app.repositories.organization import OrganizationRepository
from app.repositories.repo_graph_cache import RepoGraphCacheRepository
from app.scan.session import with_session
from app.services.code_indexer import IndexResult, index_repo
from app.services.git_operations import _detect_main_branch, run_git
from app.services.scan.stages.ingest_worktree import ensure_scan_test_worktree

logger = structlog.get_logger(__name__)

DEFAULT_MAX_FILES = 50_000


async def persist_index_result(
    *,
    org_id: uuid.UUID,
    repo_id: uuid.UUID,
    head_sha: str,
    result: IndexResult,
) -> tuple[int, bool, str | None, str | None]:
    """Write the indexer output to ``cluster_cache`` and ``repo_graph_cache``.

    Each cache uses its own short-lived session so a failure on one
    doesn't poison the other. Cluster-cache write failures are swallowed
    here and returned as an error string instead of raising — the cache
    is a performance optimisation, so the scan pipeline keeps running.

    Returns:
        ``(cluster_rows_written, graph_written, cluster_error,
        graph_error)``. The error strings let callers distinguish
        silent-persistence-failure from a deliberately-skipped run.
    """
    cluster_rows_written = 0
    graph_written = False
    cluster_error: str | None = None
    graph_error: str | None = None

    async with with_session(org_id) as db:
        try:
            cc_repo = ClusterCacheRepository(db, org_id=org_id)
            rows = [
                {
                    "cluster_id": entry.cluster_id,
                    "label": entry.label,
                    "heuristic_label": entry.label,
                    "symbol_count": entry.symbol_count,
                    "cohesion": entry.cohesion,
                    "files": entry.files,
                    "symbols": entry.symbols,
                    "signature": entry.signature,
                }
                for entry in result.clusters
            ]
            cluster_rows_written = await cc_repo.replace_for_repo_sha(
                repo_id=repo_id,
                head_sha=head_sha,
                rows=rows,
            )
            await db.commit()
        except Exception as exc:
            await db.rollback()
            cluster_error = type(exc).__name__
            # Event name preserved from the previous home in
            # ``ingest.py:_persist_index_result`` so existing log-search
            # alerts and dashboards keep firing after the extraction.
            logger.error(
                "scan_ingest_cluster_cache_write_failed",
                repo_id=str(repo_id),
                error=str(exc),
                exc_info=True,
            )

    if result.graph is not None and result.graph.number_of_nodes() > 0:
        async with with_session(org_id) as db:
            try:
                rg_repo = RepoGraphCacheRepository(db, org_id=org_id)
                await rg_repo.upsert_for_sha(
                    repo_id=repo_id,
                    head_sha=head_sha,
                    graph=result.graph,
                )
                await db.commit()
                graph_written = True
            except Exception as exc:
                await db.rollback()
                graph_error = type(exc).__name__
                # Event name preserved for observability continuity.
                logger.error(
                    "scan_ingest_graph_cache_write_failed",
                    repo_id=str(repo_id),
                    error=str(exc),
                    exc_info=True,
                )

    return cluster_rows_written, graph_written, cluster_error, graph_error


async def index_and_cache(
    *,
    org_id: uuid.UUID,
    repo_id: uuid.UUID,
    repo_path: str,
    head_sha: str | None = None,
    max_files: int = DEFAULT_MAX_FILES,
    skip_fetch: bool = False,
) -> int:
    """Refresh the sandbox worktree, run the indexer, persist cluster_cache.

    Used by the PR-merge dispatcher to backfill ``cluster_cache`` rows
    for the merge SHA before computing affected clusters. The worktree
    is reset to ``origin/<main_branch>`` (which, post-merge, points at
    the merge commit) before indexing — so the indexer sees the
    post-merge file state.

    Args:
        org_id: Owning organisation.
        repo_id: Tracked repository UUID.
        repo_path: Absolute path to the tracked repo's local clone.
        head_sha: Optional override of the SHA used as the cache key.
            If ``None``, the helper reads ``HEAD`` from the worktree
            after the reset and uses that.
        max_files: Indexer cap. Defaults to ``50_000`` (same as the
            ingest stage default).
        skip_fetch: Skip the ``git fetch`` + ``git reset`` and reuse the
            worktree as-is. Defaults to ``False``. Set ``True`` when
            the caller already refreshed the worktree (e.g. the webhook
            handler that just delivered the merge SHA) — avoids paying
            another network round-trip on the PR-merge hot path.

    Returns:
        The number of ``cluster_cache`` rows written for the SHA.

    Raises:
        RuntimeError: when the main branch can't be detected, the
            indexer reports a controlled failure, or the cluster_cache
            write fails. Callers should catch and fall back rather than
            propagating — the failure is recoverable via a full scan.
    """
    main_branch = await _detect_main_branch(repo_path)
    if not main_branch:
        raise RuntimeError(
            f"cluster_index: cannot detect main branch for {repo_path!r}"
        )

    async with with_session(org_id) as db:
        org = await OrganizationRepository(db).get_by_id(org_id)

    worktree_path = await ensure_scan_test_worktree(
        repo_path,
        main_branch,
        skip_fetch=skip_fetch,
        org=org,
    )

    resolved_sha = head_sha
    if not resolved_sha:
        stdout, _, rc = await run_git(["rev-parse", "HEAD"], cwd=worktree_path)
        if rc == 0:
            resolved_sha = stdout.strip()
    if not resolved_sha:
        raise RuntimeError(
            f"cluster_index: cannot resolve HEAD sha at {worktree_path!r}"
        )

    result = await index_repo(worktree_path, head_sha=resolved_sha, max_files=max_files)
    if not result.success:
        raise RuntimeError(
            f"cluster_index: indexer failed at {resolved_sha[:8]}: {result.error}"
        )

    rows_written, _graph_written, cluster_err, _graph_err = await persist_index_result(
        org_id=org_id,
        repo_id=repo_id,
        head_sha=resolved_sha,
        result=result,
    )
    if cluster_err is not None:
        raise RuntimeError(
            f"cluster_index: cluster_cache write failed: {cluster_err}"
        )
    logger.info(
        "cluster_index_backfill_done",
        repo_id=str(repo_id),
        head_sha=resolved_sha[:8],
        rows_written=rows_written,
        indexer_elapsed_s=result.elapsed_s,
    )
    return rows_written
