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

"""Incremental ``feature_to_repo`` BACKEND-junction refresh.

The full :mod:`app.services.scan.phase_impls.backend_link` phase walks
every active frontend feature on every scan — fine for batch
synthesis, wasteful per PR merge. This helper does the same work
scoped to a small list of ``feature_ids``: re-extract their API paths,
match against the cached :class:`BackendIndex`, and replace each
feature's BACKEND-role rows with the new set (or clear them if no
match remains).

Reads ``backend_route_cache`` (no re-extraction of backend routes —
that stage runs on the BACKEND repo's own merge); writes only the
delta to ``feature_to_repo``.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feature import Feature
from app.models.feature_to_repo import FeatureToRepo
from app.models.tracked_repository import TrackedRepository
from app.repositories.feature import FeatureRepository
from app.repositories.feature_to_repo import replace_backend_links
from app.repositories.tracked_repository import TrackedRepoRepository
from app.services.scan.backend_link.endpoint_extractor import (
    build_url_constants_map,
    extract_api_paths,
)
from app.services.scan.backend_link.linker_helpers import (
    bucket_per_repo,
    resolve_seed_paths,
)
from app.services.scan.backend_link.nuxt_autoimport import build_store_map
from app.services.scan.phase_impls.backend_link import (
    build_backend_index_from_cache,
    clear_backend_links_with_trace,
)

logger = structlog.get_logger(__name__)


@dataclass
class RefreshResult:
    """Per-call counters surfaced to the caller for logging + assertions."""

    processed: int = 0
    linked: int = 0
    cleared: int = 0
    seed_empty: int = 0
    no_api_paths: int = 0
    no_index_matches: int = 0
    skipped_no_primary: int = 0
    skipped_repo_missing: int = 0
    affected_feature_ids: list[uuid.UUID] = field(default_factory=list)


async def refresh_backend_links_for_features(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    feature_ids: Iterable[uuid.UUID],
) -> RefreshResult:
    """Re-run BACKEND-junction discovery for just these features.

    Per feature:

    1. Load the feature + its PRIMARY junction (where ``code_locations``
       lives) + the frontend repo the PRIMARY points at.
    2. Walk the feature's seed files via :func:`extract_api_paths`.
    3. :func:`bucket_per_repo` against the shared :class:`BackendIndex`.
    4. :func:`replace_backend_links` (or :func:`clear_backend_links_with_trace`
       when no match).

    Per-frontend-repo helpers (``build_url_constants_map``,
    ``build_store_map``) are cached so multiple features touching the
    same frontend don't re-walk the worktree.
    """
    feature_ids_list = list(feature_ids)
    result = RefreshResult()
    if not feature_ids_list:
        return result

    index, _backends = await build_backend_index_from_cache(db, org_id=org_id)
    if not index.paths and not index.suffix_paths:
        logger.info(
            "narrow_backend_link_index_empty",
            org_id=str(org_id),
            feature_count=len(feature_ids_list),
        )
        return result

    feat_repo = FeatureRepository(db, org_id=org_id)
    repo_repo = TrackedRepoRepository(db, org_id=org_id)
    # Per-frontend-repo caches; built lazily, reused across features
    # that share the same primary frontend.
    constants_cache: dict[uuid.UUID, dict[str, str]] = {}
    store_cache: dict[uuid.UUID, dict[str, Path]] = {}

    for feature_id in feature_ids_list:
        await _refresh_one(
            db,
            org_id=org_id,
            feature_id=feature_id,
            index=index,
            feat_repo=feat_repo,
            repo_repo=repo_repo,
            constants_cache=constants_cache,
            store_cache=store_cache,
            result=result,
        )

    await db.commit()
    logger.info(
        "narrow_backend_link_refresh_done",
        org_id=str(org_id),
        processed=result.processed,
        linked=result.linked,
        cleared=result.cleared,
        seed_empty=result.seed_empty,
        no_api_paths=result.no_api_paths,
        no_index_matches=result.no_index_matches,
        skipped_no_primary=result.skipped_no_primary,
        skipped_repo_missing=result.skipped_repo_missing,
    )
    return result


async def _refresh_one(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    feature_id: uuid.UUID,
    index: object,  # BackendIndex — typed as object to avoid the cyclic-import dance
    feat_repo: FeatureRepository,
    repo_repo: TrackedRepoRepository,
    constants_cache: dict[uuid.UUID, dict[str, str]],
    store_cache: dict[uuid.UUID, dict[str, Path]],
    result: RefreshResult,
) -> None:
    """Refresh one feature; mutates ``result`` in place.

    Pulled out so the outer loop stays at one screen of logic.
    """
    pair = await _load_feature_and_primary(feat_repo, feature_id)
    if pair is None:
        result.skipped_no_primary += 1
        return
    feature, primary_link = pair
    frontend = await repo_repo.get_by_id(primary_link.repo_id)
    if frontend is None or not frontend.path:
        result.skipped_repo_missing += 1
        return

    repo_root = Path(frontend.path)
    if not repo_root.is_dir():
        result.skipped_repo_missing += 1
        return

    result.processed += 1
    result.affected_feature_ids.append(feature_id)
    seed = resolve_seed_paths(repo_root, primary_link.code_locations)
    if not seed:
        result.seed_empty += 1
        await clear_backend_links_with_trace(
            db,
            feature_id=feature_id,
            feature_title=feature.feature_title,
            reason="narrow_seed_empty",
        )
        result.cleared += 1
        return

    constants_map = _cached_constants(constants_cache, frontend, repo_root)
    store_map = _cached_stores(store_cache, frontend, repo_root)
    api_paths = extract_api_paths(
        seed,
        constants_map=constants_map,
        repo_root=repo_root,
        store_map=store_map,
    )
    if not api_paths:
        result.no_api_paths += 1
        await clear_backend_links_with_trace(
            db,
            feature_id=feature_id,
            feature_title=feature.feature_title,
            reason="narrow_no_api_paths",
        )
        result.cleared += 1
        return

    buckets = bucket_per_repo(api_paths, index)  # type: ignore[arg-type]
    if not buckets:
        result.no_index_matches += 1
        await clear_backend_links_with_trace(
            db,
            feature_id=feature_id,
            feature_title=feature.feature_title,
            reason="narrow_no_index_matches",
        )
        result.cleared += 1
        return

    await replace_backend_links(
        db,
        feature_id=feature_id,
        feature_title=feature.feature_title,
        backend_repos=[(repo_id, b.api_paths, b.code_locations) for repo_id, b in buckets.items()],
    )
    result.linked += 1


async def _load_feature_and_primary(
    feat_repo: FeatureRepository, feature_id: uuid.UUID
) -> tuple[Feature, FeatureToRepo] | None:
    """Hydrate one feature + its PRIMARY junction.

    Returns ``None`` when either is missing — features without a PRIMARY
    junction are out of scope (BACKEND junctions are derived from the
    PRIMARY repo's ``code_locations``).
    """
    feature = await feat_repo.get_by_id(feature_id)
    if feature is None:
        return None
    primary = await feat_repo.find_primary_link(feature_id)
    if primary is None:
        return None
    return feature, primary


def _cached_constants(
    cache: dict[uuid.UUID, dict[str, str]],
    frontend: TrackedRepository,
    repo_root: Path,
) -> dict[str, str]:
    existing = cache.get(frontend.id)
    if existing is None:
        existing = build_url_constants_map(repo_root)
        cache[frontend.id] = existing
    return existing


def _cached_stores(
    cache: dict[uuid.UUID, dict[str, Path]],
    frontend: TrackedRepository,
    repo_root: Path,
) -> dict[str, Path]:
    existing = cache.get(frontend.id)
    if existing is None:
        existing = build_store_map(repo_root)
        cache[frontend.id] = existing
    return existing
