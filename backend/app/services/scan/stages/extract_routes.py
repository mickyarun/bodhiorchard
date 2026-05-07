# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Per-repo stage that caches a backend repo's HTTP route declarations.

Runs after :mod:`synthesize` for every repo, but only does real work
when the repo's ``repo_layer`` is ``BACKEND``. The output —
``backend_route_cache`` rows keyed on ``(repo_id, head_sha)`` — is
read by the global :mod:`backend_link` phase to assemble its
in-memory :class:`BackendIndex`.

Cache semantics mirror :mod:`ingest`: a re-scan with no commits is a
straight cache hit (single ``EXISTS`` lookup); only a new commit on a
backend repo invalidates and triggers a fresh walk.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import structlog

from app.models.repo_layer import RepoLayer
from app.repositories.backend_route_cache import BackendRouteCacheRepository
from app.repositories.tracked_repository import TrackedRepoRepository
from app.scan.session import with_session
from app.schemas.scan import Community
from app.services.scan.backend_link import iter_route_records
from app.services.scan.stages import StageContext, StageOutput
from app.services.scan.stages._runtime_context import resolve_runtime_context

logger = structlog.get_logger(__name__)


async def run(
    ctx: StageContext,
    communities: list[Community],
    config: dict[str, Any],
) -> StageOutput:
    """Walk the worktree and persist HTTP route declarations.

    Returns ``communities=[]`` because this stage isn't part of the
    cluster reduction chain. Counts are reported via ``extras`` so the
    chip popover can show "47 routes cached" / "skipped (cache hit)".
    """
    runtime = resolve_runtime_context(config)
    repo_id_raw = config.get("repo_id")
    if runtime is None or repo_id_raw is None:
        return StageOutput(communities=[], dropped=[], extras={"skipped": True})

    repo_id = uuid.UUID(str(repo_id_raw))
    head_sha = str(config.get("ingest_head_sha") or "").strip()

    async with with_session(runtime.org_id) as db:
        tracked = await TrackedRepoRepository(db, org_id=runtime.org_id).get_by_id(repo_id)
    if tracked is None or tracked.repo_layer is not RepoLayer.BACKEND:
        logger.info(
            "scan_extract_routes_skipped_non_backend",
            repo=ctx.repo_name,
            layer=str(tracked.repo_layer) if tracked else None,
        )
        return StageOutput(
            communities=[],
            dropped=[],
            extras={
                "skipped": True,
                "skipped_reason": "non-backend repo",
                "input_count": 0,
                "kept_count": 0,
                "io_label": "routes → cached",
            },
        )

    if not head_sha:
        # Without a SHA we can't cache. Run the extraction in-memory but
        # skip persistence — the global linker will still see the routes
        # via the next scan that does have a SHA.
        logger.warning(
            "scan_extract_routes_no_head_sha",
            repo=ctx.repo_name,
            hint="ingest stage did not produce a head_sha; skipping cache write.",
        )
        return StageOutput(
            communities=[],
            dropped=[],
            extras={
                "skipped": True,
                "skipped_reason": "no head_sha from ingest",
                "input_count": 0,
                "kept_count": 0,
                "io_label": "routes → cached",
            },
        )

    async with with_session(runtime.org_id) as db:
        cache_repo = BackendRouteCacheRepository(db, org_id=runtime.org_id)
        if await cache_repo.has_rows_for_sha(repo_id=repo_id, head_sha=head_sha):
            logger.info(
                "scan_extract_routes_cache_hit",
                repo=ctx.repo_name,
                head_sha=head_sha[:8],
            )
            return StageOutput(
                communities=[],
                dropped=[],
                extras={
                    "skipped_unchanged": True,
                    "skipped_reason": f"head_sha unchanged: {head_sha[:8]}",
                    "head_sha": head_sha,
                    "input_count": 0,
                    "kept_count": 0,
                    "io_label": "routes → cached",
                },
            )

    # Cache miss — walk the worktree and persist.
    worktree_path = config.get("v2_worktree_path") or ctx.repo_path
    repo_root = Path(str(worktree_path))
    records = list(iter_route_records(repo_root))

    async with with_session(runtime.org_id) as db:
        cache_repo = BackendRouteCacheRepository(db, org_id=runtime.org_id)
        written = await cache_repo.replace_for_repo_sha(
            repo_id=repo_id, head_sha=head_sha, records=records
        )
        await db.commit()

    extras = {
        "head_sha": head_sha,
        "input_count": len(records),
        "kept_count": written,
        "io_label": "routes → cached",
    }
    logger.info(
        "scan_extract_routes_done",
        repo=ctx.repo_name,
        head_sha=head_sha[:8],
        records=len(records),
        written=written,
    )
    return StageOutput(communities=[], dropped=[], extras=extras)
