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

"""Read-side queries for the ``features`` table.

Companion to ``app.repositories.feature.FeatureRepository``: that file
owns writes + simple identity reads; this file owns the heavier reads
needed by the new ``/v1/features`` endpoints, the tree collectors, and
the feature reconciler. Keeping them separate keeps each file focused
and under the project's soft line budget.

All methods are org-scoped via the constructor's ``org_id`` and apply
``Feature.is_active`` filtering by default — only the reconciler bulk
load opts into reading inactive rows (so they can be revived).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.feature import Feature
from app.models.feature_to_repo import FeatureToRepo, FeatureToRepoRole
from app.models.tracked_repository import TrackedRepository


@dataclass(frozen=True, slots=True)
class ReconcilerCandidate:
    """Pre-loaded snapshot of one existing feature for the reconciler.

    Carries everything the layered identity matcher needs (signature,
    code_locations from the PRIMARY junction, embedding, active flag)
    so the reconciler can do the full diff in a single bulk-load round
    trip.
    """

    feature_id: uuid.UUID
    feature_title: str
    cluster_signature: str
    code_locations: dict[str, list[str]] | None
    embedding: list[float] | None
    is_active: bool
    tags: list[str]


class FeatureReadRepository:
    """Read-only feature queries for API + tree + reconciler use cases."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        """Initialise with an async session and the org scope."""
        self._db = db
        self._org_id = org_id

    # ``feature_status`` values that mean "BUD work-in-progress" — rows
    # describing planned/in-flight work, not shipped capabilities. The
    # ``in_progress`` view mode filters to *only* these; ``active``
    # filters them out; ``all`` includes both. Single source of truth
    # for the membership test.
    _IN_PROGRESS_STATUSES: tuple[str, ...] = ("planned", "in_progress")

    # Valid ``view_mode`` values. Unknown strings fall through to
    # ``all`` (the safest default — never accidentally hides rows).
    VIEW_MODE_ALL = "all"
    VIEW_MODE_ACTIVE = "active"
    VIEW_MODE_IN_PROGRESS = "in_progress"
    VIEW_MODE_DEACTIVATED = "deactivated"

    async def list_with_links(
        self,
        *,
        repo_id: uuid.UUID | None = None,
        q: str | None = None,
        limit: int = 24,
        offset: int = 0,
        view_mode: str = VIEW_MODE_ALL,
    ) -> list[Feature]:
        """Paginated features with junctions eager-loaded.

        ``view_mode`` is one of:

        * ``"all"`` (default) — every active row regardless of
          ``feature_status``. The Features tab's default; mixes
          shipped + BUD work-in-progress together so a single page
          answers "what does this codebase have right now?".
        * ``"active"`` — only shipped / live rows
          (``feature_status IS NULL OR feature_status='implemented'``).
          Hides BUD work-in-progress.
        * ``"in_progress"`` — only BUD work-in-progress rows
          (``feature_status IN ('planned', 'in_progress')``).
        * ``"deactivated"`` — only soft-deleted rows
          (``is_active=false``).

        Filter shape otherwise mirrors the legacy
        ``/v1/skills/knowledge`` endpoint: optional ``repo_id``
        (PRIMARY junction match), optional case-insensitive ``q``
        substring on ``feature_title``.
        """
        stmt = (
            select(Feature)
            .where(Feature.org_id == self._org_id)
            .options(selectinload(Feature.repo_links))
            .order_by(Feature.feature_title)
            .limit(limit)
            .offset(offset)
        )
        stmt = self._apply_view_mode(stmt, view_mode)
        if repo_id is not None:
            stmt = stmt.join(FeatureToRepo, FeatureToRepo.feature_id == Feature.id).where(
                FeatureToRepo.repo_id == repo_id,
                FeatureToRepo.role == FeatureToRepoRole.PRIMARY,
            )
        if q:
            stmt = stmt.where(Feature.feature_title.ilike(f"%{q}%"))
        result = await self._db.execute(stmt)
        return list(result.scalars().unique().all())

    async def count_with_links(
        self,
        *,
        repo_id: uuid.UUID | None = None,
        q: str | None = None,
        view_mode: str = VIEW_MODE_ALL,
    ) -> int:
        """Total row count matching the same filters as ``list_with_links``.

        Critically uses the same ``view_mode`` predicate so the
        paginator's ``total`` agrees with the actual visible rows —
        divergence here breaks the page-count UI.
        """
        stmt = select(func.count(func.distinct(Feature.id))).where(Feature.org_id == self._org_id)
        stmt = self._apply_view_mode(stmt, view_mode)
        if repo_id is not None:
            stmt = stmt.join(FeatureToRepo, FeatureToRepo.feature_id == Feature.id).where(
                FeatureToRepo.repo_id == repo_id,
                FeatureToRepo.role == FeatureToRepoRole.PRIMARY,
            )
        if q:
            stmt = stmt.where(Feature.feature_title.ilike(f"%{q}%"))
        return int((await self._db.execute(stmt)).scalar_one() or 0)

    def _apply_view_mode(self, stmt: Any, view_mode: str) -> Any:
        """Single source of truth for the view-mode → SQL predicate.

        Both ``list_with_links`` and ``count_with_links`` route through
        here so the page can't show ``total=12`` while only 9 rows
        materialise. Unknown ``view_mode`` strings fall through to
        ``all`` as a safety default — better to show too much than to
        silently hide everything.
        """
        if view_mode == self.VIEW_MODE_DEACTIVATED:
            return stmt.where(Feature.is_active.is_(False))
        if view_mode == self.VIEW_MODE_IN_PROGRESS:
            return stmt.where(
                Feature.is_active.is_(True),
                Feature.feature_status.in_(self._IN_PROGRESS_STATUSES),
            )
        if view_mode == self.VIEW_MODE_ACTIVE:
            # ``NULL NOT IN (...)`` evaluates to NULL in three-valued
            # SQL, which would silently filter out scan-authored rows
            # (their ``feature_status`` is null). Explicit ``IS NULL``
            # branch keeps them visible while excluding rows whose
            # status is *explicitly* one of the in-progress values.
            return stmt.where(
                Feature.is_active.is_(True),
                or_(
                    Feature.feature_status.is_(None),
                    Feature.feature_status.notin_(self._IN_PROGRESS_STATUSES),
                ),
            )
        # ``all`` (default + unknown fallback) — any active row.
        return stmt.where(Feature.is_active.is_(True))

    async def get_with_links(self, feature_id: uuid.UUID) -> Feature | None:
        """Single feature with both PRIMARY + BACKEND junctions loaded."""
        stmt = (
            select(Feature)
            .where(Feature.org_id == self._org_id, Feature.id == feature_id)
            .options(selectinload(Feature.repo_links))
        )
        result = await self._db.execute(stmt)
        return result.scalars().first()

    async def list_features_with_repo_paths(
        self,
    ) -> list[
        tuple[uuid.UUID, str | None, str | None, str | None, dict[str, Any] | None, str | None]
    ]:
        """Per-repo rows for every active feature.

        Returns ``(feature_id, title, source_ref, feature_status,
        code_locations, repo_path)`` tuples — one row per PRIMARY
        junction. Features without a junction (BUD-authored,
        ``source='bud'``) appear once with ``repo_path=None`` so the
        dashboard tree can still surface them under "unbound".
        """
        stmt = (
            select(
                Feature.id.label("fid"),
                Feature.feature_title,
                Feature.source_ref,
                Feature.feature_status,
                FeatureToRepo.code_locations,
                TrackedRepository.path.label("repo_path"),
            )
            .outerjoin(
                FeatureToRepo,
                (FeatureToRepo.feature_id == Feature.id)
                & (FeatureToRepo.role == FeatureToRepoRole.PRIMARY),
            )
            .outerjoin(
                TrackedRepository,
                TrackedRepository.id == FeatureToRepo.repo_id,
            )
            .where(
                Feature.org_id == self._org_id,
                Feature.is_active.is_(True),
            )
            .order_by(Feature.synthesized_at.desc())
        )
        result = await self._db.execute(stmt)
        return [
            (
                row.fid,
                row.feature_title,
                row.source_ref,
                row.feature_status,
                row.code_locations,
                row.repo_path,
            )
            for row in result.all()
        ]

    async def feature_paths_for_repo(
        self, repo_id: uuid.UUID
    ) -> list[tuple[str, list[str], uuid.UUID]]:
        """``(feature_title, [path_prefix], feature_id)`` triples.

        Used by ``tree_db_collectors`` and ``git_analyzer`` to map
        every active feature in a repo to the source-side file
        prefixes that constitute it. Reads the PRIMARY junction's
        ``code_locations`` JSON; collapses ``frontend``/``backend``
        buckets into a flat path list (the consumers don't care which
        bucket the path came from for their use case).
        """
        stmt = (
            select(Feature.id, Feature.feature_title, FeatureToRepo.code_locations)
            .join(FeatureToRepo, FeatureToRepo.feature_id == Feature.id)
            .where(
                Feature.org_id == self._org_id,
                Feature.is_active.is_(True),
                FeatureToRepo.repo_id == repo_id,
                FeatureToRepo.role == FeatureToRepoRole.PRIMARY,
            )
        )
        result = await self._db.execute(stmt)
        out: list[tuple[str, list[str], uuid.UUID]] = []
        for fid, title, locations in result.all():
            paths = _flatten_locations(locations)
            if paths:
                out.append((title, paths, fid))
        return out

    async def backend_repo_names_for_features(
        self,
        feature_ids: list[uuid.UUID],
    ) -> dict[uuid.UUID, list[str]]:
        """``{feature_id: [backend_repo_name, …]}`` for a batch of features.

        Reads BACKEND junction rows and resolves each ``repo_id`` to
        ``TrackedRepository.name`` so callers that already key by repo
        name (e.g. the dashboard tree's ``linked_repos``) don't need a
        second lookup. Backend names within a feature are returned
        sorted alphabetically so arc rendering and detail-panel listing
        are deterministic across reloads.
        """
        if not feature_ids:
            return {}
        stmt = (
            select(
                FeatureToRepo.feature_id,
                TrackedRepository.name.label("repo_name"),
            )
            .join(Feature, Feature.id == FeatureToRepo.feature_id)
            .join(TrackedRepository, TrackedRepository.id == FeatureToRepo.repo_id)
            .where(
                Feature.org_id == self._org_id,
                Feature.is_active.is_(True),
                FeatureToRepo.feature_id.in_(feature_ids),
                FeatureToRepo.role == FeatureToRepoRole.BACKEND,
            )
            .order_by(FeatureToRepo.feature_id, TrackedRepository.name)
        )
        result = await self._db.execute(stmt)
        grouped: dict[uuid.UUID, list[str]] = {}
        for fid, repo_name in result.all():
            grouped.setdefault(fid, []).append(repo_name)
        return grouped

    async def semantic_search(
        self,
        query_vector: list[float],
        *,
        limit: int = 10,
        offset: int = 0,
        only_active: bool = True,
    ) -> list[tuple[Feature, float]]:
        """Cosine-distance semantic search over ``Feature.embedding``.

        Returns ``(feature, distance)`` tuples sorted ascending by
        distance (smallest first = most similar). ``offset`` enables
        cursor-free pagination — the MCP ``get_features`` tool surfaces
        it so an external LLM can iterate through more than ``limit``
        matches in orgs with hundreds of features.
        """
        distance = Feature.embedding.cosine_distance(query_vector).label("distance")
        stmt = (
            select(Feature, distance)
            .where(
                Feature.org_id == self._org_id,
                Feature.embedding.isnot(None),
            )
            .order_by(distance)
            .offset(offset)
            .limit(limit)
        )
        if only_active:
            stmt = stmt.where(Feature.is_active.is_(True))
        result = await self._db.execute(stmt)
        return [(row.Feature, float(row.distance)) for row in result.all()]

    async def bulk_load_for_reconcile(
        self,
        repo_id: uuid.UUID,
        *,
        include_inactive: bool = True,
    ) -> list[ReconcilerCandidate]:
        """Single-query snapshot of every feature in ``repo_id``.

        The reconciler matches synthesised entries against this list
        via signature → Jaccard → cosine fallback. Includes inactive
        features by default so soft-deleted rows can be revived.
        """
        stmt = (
            select(
                Feature.id,
                Feature.feature_title,
                Feature.cluster_signature,
                Feature.embedding,
                Feature.is_active,
                Feature.tags,
                FeatureToRepo.code_locations,
            )
            .join(FeatureToRepo, FeatureToRepo.feature_id == Feature.id)
            .where(
                Feature.org_id == self._org_id,
                FeatureToRepo.repo_id == repo_id,
                FeatureToRepo.role == FeatureToRepoRole.PRIMARY,
            )
        )
        if not include_inactive:
            stmt = stmt.where(Feature.is_active.is_(True))
        result = await self._db.execute(stmt)
        return [
            ReconcilerCandidate(
                feature_id=row.id,
                feature_title=row.feature_title,
                cluster_signature=row.cluster_signature,
                code_locations=row.code_locations,
                embedding=list(row.embedding) if row.embedding is not None else None,
                is_active=row.is_active,
                tags=list(row.tags or []),
            )
            for row in result.all()
        ]


def _flatten_locations(locations: dict[str, Any] | None) -> list[str]:
    """Flatten ``{frontend: [...], backend: [...]}`` into a sorted list.

    Tolerates the legacy single-list shape and an empty dict; returns
    ``[]`` when ``locations`` is None.
    """
    if not locations:
        return []
    paths: list[str] = []
    for value in locations.values():
        if isinstance(value, list):
            paths.extend(str(p) for p in value if isinstance(p, str))
    return sorted(set(paths))
