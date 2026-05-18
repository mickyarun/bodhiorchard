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

"""Inline ``backend_route_cache`` backfill for the narrow PR-merge path.

The full :mod:`app.services.scan.stages.extract_routes` stage runs as
part of a complete scan — wasteful per PR merge. This helper mirrors
its logic without the stage plumbing so the PR-merge dispatcher can
backfill cached routes inline:

1. Layer-gate to ``RepoLayer.BACKEND`` — non-backend repos no-op.
2. Cache-hit check on ``(repo_id, head_sha)`` — re-runs short-circuit.
3. Walk the worktree via :func:`iter_route_records` (the same producer
   the full-scan stage and the in-memory index assembler share).
4. Bulk-upsert via
   :meth:`BackendRouteCacheRepository.replace_for_repo_sha`.

Failures are surfaced via the return tuple, never raised — the caller
treats a refresh failure the same as a non-backend repo (skip the
cross-layer junction work). The downstream linker continues to work
against the previous SHA's cache rows, so a one-off failure costs
freshness but not correctness.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import structlog

from app.database import AsyncSessionLocal
from app.models.repo_layer import RepoLayer
from app.repositories.backend_route_cache import BackendRouteCacheRepository
from app.repositories.tracked_repository import TrackedRepoRepository
from app.services.scan.backend_link.backend_indexer import iter_route_records

logger = structlog.get_logger(__name__)


async def index_and_cache_backend_routes(
    *,
    org_id: uuid.UUID,
    repo_id: uuid.UUID,
    head_sha: str,
) -> int:
    """Walk the repo at ``head_sha`` and upsert ``backend_route_cache`` rows.

    Returns the number of route records written. ``0`` means: non-
    backend repo, cache already populated for this SHA, repo path
    missing, or worktree empty of route declarations.

    Owns its own DB session — the caller doesn't need to keep one
    open across the worktree walk (which can take 100s of ms on
    large repos).
    """
    async with AsyncSessionLocal() as db:
        tracked = await TrackedRepoRepository(db, org_id=org_id).get_by_id(repo_id)
        if tracked is None or tracked.repo_layer is not RepoLayer.BACKEND:
            return 0
        if not tracked.path:
            logger.info(
                "narrow_route_index_skipped_no_path",
                repo_id=str(repo_id),
                head_sha=head_sha[:8],
            )
            return 0
        cache_repo = BackendRouteCacheRepository(db, org_id=org_id)
        if await cache_repo.has_rows_for_sha(repo_id=repo_id, head_sha=head_sha):
            logger.info(
                "narrow_route_index_cache_hit",
                repo_id=str(repo_id),
                head_sha=head_sha[:8],
            )
            return 0
        repo_root = Path(tracked.path)

    # Worktree walk runs OUTSIDE the DB session — synchronous + IO-bound
    # but never touches the DB connection, so holding the session open
    # would block other writers for no benefit.
    records = list(iter_route_records(repo_root))

    async with AsyncSessionLocal() as db:
        cache_repo = BackendRouteCacheRepository(db, org_id=org_id)
        written = await cache_repo.replace_for_repo_sha(
            repo_id=repo_id, head_sha=head_sha, records=records
        )
        # Advance the tracked repo's head_sha so the BACKEND-route index
        # builder (which keys cache lookups by ``tracked_repositories.head_sha``)
        # sees these rows. The narrow merge has successfully processed
        # commits up to this SHA — semantically this is "what we've
        # processed", not "what was last fully scanned".
        await TrackedRepoRepository(db, org_id=org_id).advance_head_sha(
            repo_id=repo_id, head_sha=head_sha
        )
        await db.commit()

    logger.info(
        "narrow_route_index_done",
        repo_id=str(repo_id),
        head_sha=head_sha[:8],
        records=len(records),
        written=written,
    )
    return written
