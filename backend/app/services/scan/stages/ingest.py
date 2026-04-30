# SPDX-License-Identifier: MIT
# Copyright (C) 2026 Arun Rajkumar

"""Stage 0 — Ingest. Refresh a sandbox worktree and run the code indexer.

Side-effectful: creates a worktree at ``<repo>/.bodhiorchard/scan-test/<branch>``
(distinct from the production ``<repo>/.bodhiorchard/main`` worktree so live
scans aren't affected), force-resets it to ``origin/<main_branch>``, then
runs ``app.services.code_indexer.index_repo`` against it.

The indexer (a thin wrapper over the MIT-licensed ``graphifyy`` library)
parses files with tree-sitter, builds a NetworkX call graph, and runs
Leiden / Louvain community detection. Output is written to two caches
keyed on ``(repo_id, head_sha)``:

- ``cluster_cache``: one row per community, used by Stage 1 (extract).
- ``repo_graph_cache``: one row per (repo, head_sha) holding the gzipped
  NetworkX graph as JSON node-link bytes. Used by Stage 3 (hierarchical)
  and the ``code_impact`` MCP tool group.

Skip-on-cache-hit is delegated to ``should_skip_indexing`` in
``_skip_predicates``. When it returns ``skip=True`` the stage emits a
uniform skipped output so the chip popover and downstream reduction
stages see consistent metadata.
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog

from app.repositories.cluster_cache import ClusterCacheRepository
from app.repositories.repo_graph_cache import RepoGraphCacheRepository
from app.scan.session import with_session
from app.schemas.scan import Community
from app.services.code_indexer import IndexResult, index_repo
from app.services.git_operations import _detect_main_branch, run_git
from app.services.scan.stages import StageContext, StageOutput
from app.services.scan.stages._skip import stage_output_for_skip
from app.services.scan.stages._skip_predicates import (
    should_skip_feature_synthesis,
    should_skip_indexing,
)
from app.services.scan.stages._v2_context import resolve_v2_context
from app.services.scan.stages.ingest_worktree import ensure_scan_test_worktree

logger = structlog.get_logger(__name__)


async def run(
    ctx: StageContext,
    communities: list[Community],
    config: dict[str, Any],
) -> StageOutput:
    """Refresh sandbox worktree + run the code indexer.

    ``communities`` is ignored (Stage 0 has no upstream input). ``config``
    accepts:
        - ``main_branch`` (str | None): override the detected main branch.
        - ``analyze_timeout`` (int): seconds, default 600.
        - ``skip_fetch`` (bool): default False — set True to reuse the
          worktree as-is (useful for unit tests without network).
        - ``force_reindex`` (bool): default False — set True to bypass
          ``should_skip_indexing`` and re-run the indexer even when the
          cache is fresh.
        - ``max_files`` (int): cap on files indexed; default 50_000.
    """
    main_branch = config.get("main_branch") or await _detect_main_branch(ctx.repo_path)
    if not main_branch:
        raise RuntimeError(
            f"Cannot detect main branch for {ctx.repo_path!r}. "
            "Set config.ingest.main_branch explicitly."
        )

    worktree_path = await ensure_scan_test_worktree(
        ctx.repo_path,
        main_branch,
        skip_fetch=bool(config.get("skip_fetch", False)),
    )

    head_sha = ""
    if not config.get("skip_fetch", False):
        stdout, _, rc = await run_git(["rev-parse", "HEAD"], cwd=worktree_path)
        if rc == 0:
            head_sha = stdout.strip()

    v2 = resolve_v2_context(config)
    repo_id_raw = config.get("v2_repo_id")

    if v2 is not None and repo_id_raw is not None:
        repo_id = uuid.UUID(str(repo_id_raw))
        async with with_session(v2.org_id) as db:
            decision = await should_skip_indexing(
                db,
                org_id=v2.org_id,
                repo_id=repo_id,
                head_sha=head_sha,
                force_reindex=bool(config.get("force_reindex", False)),
            )
            propagate_skip = True
            if decision.skip:
                synth_decision = await should_skip_feature_synthesis(
                    db,
                    org_id=v2.org_id,
                    repo_id=repo_id,
                    repo_path=ctx.repo_path,
                    full_rescan=bool(config.get("v2_full_rescan", False)),
                )
                propagate_skip = synth_decision.skip
        if decision.skip:
            skipped_extras = stage_output_for_skip(decision, io_label="repo → indexed").extras
            skipped_extras.update(
                {
                    "worktree_path": worktree_path,
                    "main_branch": main_branch,
                    "head_sha": head_sha,
                    "stats": {},
                    "input_count": 1,
                }
            )
            if not propagate_skip:
                # Indexing stays skipped (cache is fresh) but the reduction
                # chain must run so synthesize sees communities.
                skipped_extras["skipped_unchanged"] = False
                skipped_extras["skipped_reason"] = (
                    f"{decision.reason or 'cache hit'}; "
                    "downstream synthesis missing → reduction chain forced"
                )
            logger.info(
                "scan_ingest_skipped",
                repo=ctx.repo_name,
                head_sha=head_sha[:8] if head_sha else "",
                reason=decision.reason,
                propagated=propagate_skip,
            )
            return StageOutput(communities=[], dropped=[], extras=skipped_extras)

    # Cache miss — run the indexer.
    max_files = int(config.get("max_files", 50_000))
    result = await index_repo(
        worktree_path,
        head_sha=head_sha,
        max_files=max_files,
    )

    if not result.success:
        # Indexer reported a controlled failure (oversized repo, parse
        # error, etc.). Surface as a stage error so the scan stops.
        raise RuntimeError(f"code_indexer failed for {ctx.repo_name!r}: {result.error}")

    # Persist results to both caches when we have a v2 context.
    cache_written = 0
    graph_written = False
    cluster_cache_error: str | None = None
    graph_cache_error: str | None = None
    if v2 is not None and repo_id_raw is not None and head_sha:
        repo_id = uuid.UUID(str(repo_id_raw))
        (
            cache_written,
            graph_written,
            cluster_cache_error,
            graph_cache_error,
        ) = await _persist_index_result(
            org_id=v2.org_id,
            repo_id=repo_id,
            head_sha=head_sha,
            result=result,
        )

    stats = {
        "communities": len(result.clusters),
        "nodes": result.graph.number_of_nodes() if result.graph is not None else 0,
        "edges": result.graph.number_of_edges() if result.graph is not None else 0,
        "files": result.file_count,
    }

    extras: dict[str, Any] = {
        "worktree_path": worktree_path,
        "main_branch": main_branch,
        "head_sha": head_sha,
        "stats": stats,
        "skipped_unchanged": False,
        "input_count": 1,
        "io_label": "repo → indexed",
        "cluster_rows_written": cache_written,
        "graph_written": graph_written,
        "indexer_elapsed_s": result.elapsed_s,
    }
    # Surface cache-write failures so the chip popover and downstream
    # "cache miss" warnings can distinguish silent persistence failure
    # from a deliberately-skipped run.
    if cluster_cache_error is not None:
        extras["cluster_cache_write_error"] = cluster_cache_error
    if graph_cache_error is not None:
        extras["graph_cache_write_error"] = graph_cache_error
    logger.info(
        "scan_ingest_done",
        repo=ctx.repo_name,
        head_sha=head_sha[:8],
        communities=stats["communities"],
        nodes=stats["nodes"],
        edges=stats["edges"],
    )
    return StageOutput(communities=[], dropped=[], extras=extras)


async def _persist_index_result(
    *,
    org_id: uuid.UUID,
    repo_id: uuid.UUID,
    head_sha: str,
    result: IndexResult,
) -> tuple[int, bool, str | None, str | None]:
    """Write the indexer output to ``cluster_cache`` and ``repo_graph_cache``.

    Returns:
        ``(cluster_rows_written, graph_written, cluster_error,
        graph_error)``. Cache write failures are caught and surfaced via
        the error strings so the stage's ``extras`` can report the
        partial state to the chip popover — the caches are a performance
        optimisation and the scan should keep running, but operators
        need to be able to tell silent-persistence-failure apart from a
        deliberately-skipped run.
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
                logger.error(
                    "scan_ingest_graph_cache_write_failed",
                    repo_id=str(repo_id),
                    error=str(exc),
                    exc_info=True,
                )

    return cluster_rows_written, graph_written, cluster_error, graph_error
