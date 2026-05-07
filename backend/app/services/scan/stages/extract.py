# SPDX-License-Identifier: MIT
# Copyright (C) 2026 Arun Rajkumar

"""Stage 1 — Hydrate ``Community`` rows from the cluster cache.

Stage 0 (``ingest``) runs the code indexer (``app.services.code_indexer``)
which both clusters the repo with graphify and writes the result to
``cluster_cache``. This stage just hydrates the cached rows back into
``Community`` objects for downstream reduction stages (filter_infra,
size_floor, top_n, hierarchical, …).

Two cost layers, in order of preference:

1. **Postgres cache hit** — when the context provides
   ``(repo_id, head_sha)`` and ``cluster_cache`` has rows for that
   pair, hydrate from Postgres in one query. ~50ms.
2. **Cache miss** — log a warning and return an empty list. The new
   code indexer is the only producer; if rows are missing it means
   ingest was skipped or failed, and downstream stages will surface
   the empty input cleanly.

This is a much smaller stage than the legacy GitNexus version: there
is no cypher fan-out, no NPX subprocess management, no per-community
file fetch.
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog

from app.repositories.cluster_cache import ClusterCacheRepository
from app.scan.session import with_session
from app.schemas.scan import Community
from app.services.scan.stages import StageContext, StageOutput
from app.services.scan.stages._runtime_context import resolve_runtime_context
from app.services.scan.stages._skip import maybe_skipped_for_ingest

logger = structlog.get_logger(__name__)


async def run(
    ctx: StageContext,
    communities: list[Community],
    config: dict[str, Any],
) -> StageOutput:
    """Hydrate ``Community`` rows from ``cluster_cache``.

    ``communities`` is ignored (Stage 1 has no upstream input — Stage 0
    writes the cache, Stage 1 reads it).
    """
    skipped = maybe_skipped_for_ingest(config, io_label="indexer → communities")
    if skipped is not None:
        return skipped

    files_per = int(config.get("files_per_community", 15))

    runtime = resolve_runtime_context(config)
    repo_id_raw = config.get("repo_id")
    head_sha = str(config.get("ingest_head_sha") or "").strip()

    if runtime is None or repo_id_raw is None or not head_sha:
        # Without a context there is no cache to hit; the prior
        # path is gone with GitNexus. Return an empty stage output and
        # let downstream stages handle the no-input case.
        logger.info(
            "scan_extract_no_runtime_context",
            repo=ctx.repo_name,
            has_runtime=runtime is not None,
            has_repo_id=repo_id_raw is not None,
            has_head_sha=bool(head_sha),
        )
        return StageOutput(
            communities=[],
            dropped=[],
            extras={
                "total_communities": 0,
                "files_per_community": files_per,
                "io_label": "indexer → communities",
                "cache_hit": False,
                "reason": "no context",
            },
        )

    repo_id = uuid.UUID(str(repo_id_raw))
    cached = await _load_cached_communities(
        org_id=runtime.org_id, repo_id=repo_id, head_sha=head_sha
    )

    if cached is None:
        logger.warning(
            "scan_extract_cache_miss",
            repo=ctx.repo_name,
            head_sha=head_sha[:8],
            message="no cluster_cache rows — was Stage 0 (ingest) run?",
        )
        return StageOutput(
            communities=[],
            dropped=[],
            extras={
                "total_communities": 0,
                "files_per_community": files_per,
                "io_label": "indexer → communities",
                "cache_hit": False,
                "head_sha": head_sha,
                "reason": "cluster_cache empty",
            },
        )

    logger.info(
        "scan_extract_cache_hit",
        repo=ctx.repo_name,
        head_sha=head_sha[:8],
        community_count=len(cached),
    )
    return StageOutput(
        communities=cached,
        dropped=[],
        extras={
            "total_communities": len(cached),
            "files_per_community": files_per,
            "io_label": "indexer → communities",
            "cache_hit": True,
            "head_sha": head_sha,
        },
    )


async def _load_cached_communities(
    *,
    org_id: uuid.UUID,
    repo_id: uuid.UUID,
    head_sha: str,
) -> list[Community] | None:
    """Hydrate ``Community`` objects from the Postgres cache, or None on miss.

    Returns ``None`` when no rows exist for ``(repo_id, head_sha)``.
    Returns ``[]`` when the cache was populated but the repo genuinely
    has zero clusters (so the caller doesn't pointlessly retry).
    """
    async with with_session(org_id) as db:
        repo = ClusterCacheRepository(db, org_id=org_id)
        rows = await repo.list_for_repo_sha(repo_id=repo_id, head_sha=head_sha)
    if not rows:
        return None
    return [
        Community(
            community_id=row.cluster_id,
            label=row.label,
            heuristic_label=row.heuristic_label,
            symbol_count=row.symbol_count,
            cohesion=row.cohesion,
            files=list(row.files or []),
        )
        for row in rows
    ]
