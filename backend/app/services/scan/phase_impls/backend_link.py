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

"""Global ``backend_link`` phase — cross-layer frontend↔backend linker.

Runs once per scan, after every per-repo workflow has finished. Reads
the ``backend_route_cache`` rows produced by per-repo
:mod:`extract_routes` runs, walks each frontend repo's worktree feature
by feature, and writes the ``feature_to_repo`` BACKEND junction rows
that materialise the cross-layer graph.

Hot-loop hygiene (matches the plan's scalability section):

* The :class:`BackendIndex` is built **once** per phase invocation by
  reading every backend repo's cached routes for its current
  ``head_sha``.
* For each FRONTEND repo, the per-repo ``constants_map`` and
  ``store_map`` are built **once** and reused across every feature in
  that repo. These maps are O(repo size) so building per-feature would
  re-walk the worktree N times.
* All ``feature_to_repo`` writes for a single frontend repo are queued
  into one batched commit, not one transaction per feature.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.repo_layer import RepoLayer
from app.models.tracked_repository import TrackedRepository
from app.repositories.backend_route_cache import BackendRouteCacheRepository
from app.repositories.feature import FeatureRepository
from app.repositories.feature_to_repo import count_backend_links, replace_backend_links
from app.repositories.tracked_repository import TrackedRepoRepository
from app.scan.session import with_session
from app.services.scan.backend_link import (
    BackendIndex,
    all_suffixes,
    bucket_per_repo,
    build_store_map,
    build_url_constants_map,
    extract_api_paths,
    resolve_seed_paths,
)

logger = structlog.get_logger(__name__)


async def run_backend_link(
    *,
    org_id: uuid.UUID,
    scan_id: uuid.UUID,
) -> dict[str, int]:
    """Build the cross-layer graph for one org and persist BACKEND junction rows.

    Returns counters (``frontend_repos``, ``backend_repos_indexed``,
    ``indexed_routes``, ``features_processed``, ``features_linked``)
    for the chip popover.
    """
    async with with_session(org_id) as db:
        index, backend_repos = await _build_index_from_cache(db, org_id=org_id)
        frontend_repos = await TrackedRepoRepository(db, org_id=org_id).list_by_layer(
            RepoLayer.FRONTEND
        )

    counters = {
        "frontend_repos": len(frontend_repos),
        "backend_repos_indexed": len(backend_repos),
        "indexed_routes": len(index.paths),
        "features_processed": 0,
        "features_linked": 0,
    }

    if not frontend_repos:
        logger.info("scan_backend_link_no_frontends", org_id=str(org_id))
        return counters

    if not index.paths:
        # Every frontend's features will end up with empty buckets when
        # nothing got indexed. Surface this once at org level so a glance
        # at the log tells the operator the gap is upstream (extract_routes
        # / classification) not in this phase.
        logger.warning(
            "scan_backend_link_no_backend_routes_indexed",
            org_id=str(org_id),
            backend_repo_count=len(backend_repos),
            hint=(
                "Either no repos are classified BACKEND, or every backend "
                "repo's head_sha has no cached extract_routes rows. "
                "Linking will run but produce zero matches."
            ),
        )

    for frontend in frontend_repos:
        if not frontend.path:
            logger.warning("scan_backend_link_frontend_no_path", repo=frontend.name)
            continue
        processed, linked = await _link_one_frontend_repo(
            org_id=org_id,
            scan_id=scan_id,
            frontend=frontend,
            index=index,
        )
        counters["features_processed"] += processed
        counters["features_linked"] += linked

    logger.info(
        "scan_backend_link_done",
        scan_id=str(scan_id),
        **counters,
    )
    return counters


async def _build_index_from_cache(
    db: AsyncSession, *, org_id: uuid.UUID
) -> tuple[BackendIndex, list[TrackedRepository]]:
    """Assemble the in-memory ``BackendIndex`` from cached route rows.

    Reads each BACKEND repo's current ``head_sha`` (from
    ``tracked_repositories``) and pulls its rows from
    ``backend_route_cache``. Repos with no cached rows yet are skipped
    silently — they'll appear once their first ``extract_routes`` run
    has committed.
    """
    repo_repo = TrackedRepoRepository(db, org_id=org_id)
    cache_repo = BackendRouteCacheRepository(db, org_id=org_id)
    backends = await repo_repo.list_by_layer(RepoLayer.BACKEND)
    index = BackendIndex()
    for backend in backends:
        if not backend.head_sha:
            logger.warning(
                "scan_backend_link_backend_no_head_sha",
                repo=backend.name,
                repo_id=str(backend.id),
                hint="extract_routes can't key its cache without a head_sha; run a scan first.",
            )
            continue
        cached = await cache_repo.list_for_repo_sha(repo_id=backend.id, head_sha=backend.head_sha)
        if not cached:
            logger.warning(
                "scan_backend_link_index_empty_for_repo",
                repo=backend.name,
                repo_id=str(backend.id),
                head_sha=backend.head_sha[:8],
                hint=(
                    "extract_routes never wrote a cache row for this (repo, sha) pair. "
                    "Either the stage skipped (non-BACKEND classification) or the SHA "
                    "advanced after extraction. Re-run a scan."
                ),
            )
            continue
        for row in cached:
            full = row.normalised_path
            entry = (backend.id, row.file_path)
            index.paths.setdefault(full, set()).add(entry)
            for suffix in all_suffixes(full):
                index.suffix_paths.setdefault(suffix, set()).add(entry)
        logger.info(
            "scan_backend_link_indexed_repo",
            repo=backend.name,
            repo_id=str(backend.id),
            head_sha=backend.head_sha[:8],
            cached_routes=len(cached),
        )
    return index, backends


async def _link_one_frontend_repo(
    *,
    org_id: uuid.UUID,
    scan_id: uuid.UUID,
    frontend: TrackedRepository,
    index: BackendIndex,
) -> tuple[int, int]:
    """Link every feature in one frontend repo. Returns (processed, linked)."""
    repo_root = Path(frontend.path or "")
    if not repo_root.is_dir():
        logger.warning(
            "scan_backend_link_frontend_path_missing",
            repo=frontend.name,
            path=str(repo_root),
        )
        return 0, 0

    # Build the per-frontend-repo extraction context ONCE — these walks
    # are O(repo size) so re-running them per-feature would be the hot
    # loop's biggest cost. constants_map captures URL declarations like
    # ``const FOO = "/x"``; store_map resolves Nuxt auto-imported Pinia
    # stores so the BFS expansion can reach them without literal imports.
    constants_map = build_url_constants_map(repo_root)
    store_map = build_store_map(repo_root)

    processed = 0
    linked = 0
    seed_empty = 0
    no_api_paths = 0
    no_index_matches = 0
    async with with_session(org_id) as db:
        feature_repo = FeatureRepository(db, org_id=org_id)
        pairs = await feature_repo.list_primary_pairs_for_repo(frontend.id)
        for feature, primary_link in pairs:
            processed += 1
            seed = resolve_seed_paths(repo_root, primary_link.code_locations)
            if not seed:
                # No source files reach this feature — nothing to extract,
                # but still clear any stale BACKEND rows so a feature whose
                # files were renamed loses its prior link set.
                seed_empty += 1
                await _clear_backend_links_with_trace(
                    db,
                    feature_id=feature.id,
                    feature_title=feature.feature_title,
                    reason="seed_empty",
                )
                continue
            api_paths = extract_api_paths(
                seed,
                constants_map=constants_map,
                repo_root=repo_root,
                store_map=store_map,
            )
            if not api_paths:
                no_api_paths += 1
                await _clear_backend_links_with_trace(
                    db,
                    feature_id=feature.id,
                    feature_title=feature.feature_title,
                    reason="no_api_paths",
                )
                continue
            buckets = bucket_per_repo(api_paths, index)
            if not buckets:
                no_index_matches += 1
                await _clear_backend_links_with_trace(
                    db,
                    feature_id=feature.id,
                    feature_title=feature.feature_title,
                    reason="no_index_matches",
                )
                logger.debug(
                    "scan_backend_link_feature_trace",
                    feature_id=str(feature.id),
                    seed_count=len(seed),
                    api_paths_count=len(api_paths),
                    matched_repo_count=0,
                )
                continue
            await replace_backend_links(
                db,
                feature_id=feature.id,
                feature_title=feature.feature_title,
                backend_repos=[
                    (repo_id, b.api_paths, b.code_locations) for repo_id, b in buckets.items()
                ],
            )
            linked += 1
            logger.debug(
                "scan_backend_link_feature_trace",
                feature_id=str(feature.id),
                seed_count=len(seed),
                api_paths_count=len(api_paths),
                matched_repo_count=len(buckets),
            )
        # ONE batched commit per frontend repo — N transactions across N
        # features would be the obvious naive shape and the planning round
        # called it out as a scalability risk.
        await db.commit()

    if processed == 0:
        # Either the repo legitimately has no synthesised features, or its
        # repo_layer changed since synthesis (now FRONTEND but previously
        # something else, so PRIMARY junctions point elsewhere).
        logger.info(
            "scan_backend_link_frontend_no_features",
            repo=frontend.name,
            hint="No PRIMARY junctions point at this frontend repo.",
        )
    logger.info(
        "scan_backend_link_frontend_done",
        scan_id=str(scan_id),
        repo=frontend.name,
        processed=processed,
        seed_empty=seed_empty,
        no_api_paths=no_api_paths,
        no_index_matches=no_index_matches,
        linked=linked,
    )
    return processed, linked


async def _clear_backend_links_with_trace(
    db: AsyncSession,
    *,
    feature_id: uuid.UUID,
    feature_title: str,
    reason: str,
) -> None:
    """``replace_backend_links([])`` with a warning when prior rows existed.

    A re-scan that nukes a feature's previously-good BACKEND link set is
    silent today — same row count gets reported, no signal that anything
    regressed. This wrapper logs a warning whenever the delete affects
    ≥1 row, so a regression that flips a feature from "linked to N
    backends" to "linked to 0" surfaces in ops logs by feature_id +
    reason. The caller still gets the contractual "stale rows cleared"
    semantics.

    ``feature_title`` is forwarded so :func:`replace_backend_links`'s
    signature stays consistent across both the populate and clear paths,
    even though no new rows are inserted in the empty-list case.
    """
    existing = await count_backend_links(db, feature_id=feature_id)
    if existing > 0:
        logger.warning(
            "scan_backend_link_clearing_existing",
            feature_id=str(feature_id),
            existing_backend_links=existing,
            reason=reason,
        )
    await replace_backend_links(
        db,
        feature_id=feature_id,
        feature_title=feature_title,
        backend_repos=[],
    )
