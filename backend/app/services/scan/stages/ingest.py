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

from app.repositories.organization import OrganizationRepository
from app.scan.session import with_session
from app.schemas.scan import Community
from app.services.code_indexer import index_repo
from app.services.git_operations import _detect_main_branch, run_git
from app.services.scan.cluster_index import persist_index_result
from app.services.scan.stages import StageContext, StageOutput
from app.services.scan.stages._runtime_context import resolve_runtime_context
from app.services.scan.stages._skip import stage_output_for_skip
from app.services.scan.stages._skip_predicates import (
    should_skip_feature_synthesis,
    should_skip_indexing,
)
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

    runtime = resolve_runtime_context(config)
    org = None
    if runtime is not None:
        # Detach the org from its session — safe because AsyncSessionLocal
        # is configured with ``expire_on_commit=False`` (see
        # ``app/database.py``), so attribute access after the session
        # closes won't trigger a lazy refresh.
        async with with_session(runtime.org_id) as db:
            org = await OrganizationRepository(db).get_by_id(runtime.org_id)

    worktree_path = await ensure_scan_test_worktree(
        ctx.repo_path,
        main_branch,
        skip_fetch=bool(config.get("skip_fetch", False)),
        org=org,
    )

    head_sha = ""
    if not config.get("skip_fetch", False):
        stdout, _, rc = await run_git(["rev-parse", "HEAD"], cwd=worktree_path)
        if rc == 0:
            head_sha = stdout.strip()

    repo_id_raw = config.get("repo_id")

    if runtime is not None and repo_id_raw is not None:
        repo_id = uuid.UUID(str(repo_id_raw))
        async with with_session(runtime.org_id) as db:
            decision = await should_skip_indexing(
                db,
                org_id=runtime.org_id,
                repo_id=repo_id,
                head_sha=head_sha,
                force_reindex=bool(config.get("force_reindex", False)),
            )
            propagate_skip = True
            if decision.skip:
                synth_decision = await should_skip_feature_synthesis(
                    db,
                    org_id=runtime.org_id,
                    repo_id=repo_id,
                    repo_path=ctx.repo_path,
                    full_rescan=bool(config.get("full_rescan", False)),
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

    # Persist results to both caches when we have a context.
    cache_written = 0
    graph_written = False
    cluster_cache_error: str | None = None
    graph_cache_error: str | None = None
    if runtime is not None and repo_id_raw is not None and head_sha:
        repo_id = uuid.UUID(str(repo_id_raw))
        (
            cache_written,
            graph_written,
            cluster_cache_error,
            graph_cache_error,
        ) = await persist_index_result(
            org_id=runtime.org_id,
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


