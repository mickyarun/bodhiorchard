# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Feature data access repository (was ``SynthesizedFeatureRepository``).

Immutable, append-only feature audit. Writes happen during
``FEATURE_SYNTHESIS`` (MCP ``write_feature_registry``). The per-repo
``backend_link`` stage augments rows by inserting BACKEND junction rows
into ``feature_to_repo``; it never mutates the ``features`` row itself.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete as sql_delete
from sqlalchemy import func, select
from sqlalchemy import update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feature import Feature
from app.models.feature_to_repo import FeatureToRepo, FeatureToRepoRole
from app.repositories.base import BaseRepository


class FeatureRepository(BaseRepository[Feature]):
    """Repository for ``features`` rows, org-scoped.

    Organisation scoping is inherited from ``BaseRepository``; every
    read method applies ``org_id`` via ``_scoped``. Repo-scoped reads
    (``list_current_for_repo``, ``count_active_per_repo``,
    ``cluster_names_for_repo``) JOIN through ``feature_to_repo`` filtering
    on ``role='primary'`` — the synthesis source repo, not the linked
    backend repos.
    """

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        super().__init__(Feature, db, org_id=org_id)

    async def count_active_for_repo(self, repo_id: uuid.UUID) -> int:
        """Non-superseded feature count for one repo's PRIMARY junction.

        Used by the synthesize stage to populate the chip's "kept_count"
        without round-tripping through the full row set. Counts exactly
        the same rows the page-level :func:`count_active_per_repo` would
        return for ``repo_id`` — kept as a separate one-shot helper so
        the stage doesn't load every other repo's count just to read one.
        """
        stmt = self._scoped(
            select(func.count(Feature.id))
            .select_from(Feature)
            .join(FeatureToRepo, FeatureToRepo.feature_id == Feature.id)
            .where(
                Feature.superseded_at.is_(None),
                FeatureToRepo.repo_id == repo_id,
                FeatureToRepo.role == FeatureToRepoRole.PRIMARY,
            )
        )
        return int((await self._db.execute(stmt)).scalar_one() or 0)

    async def count_active_per_repo(self) -> dict[uuid.UUID, int]:
        """Per-repo counts of non-superseded features for the org.

        Joins through ``feature_to_repo`` on ``role='primary'`` so a
        feature is counted against the repo where it was synthesised, not
        the backend repos it links to via ``role='backend'`` rows.
        """
        stmt = self._scoped(
            select(
                FeatureToRepo.repo_id,
                func.count(Feature.id).label("synth_count"),
            )
            .join(FeatureToRepo, FeatureToRepo.feature_id == Feature.id)
            .where(
                Feature.superseded_at.is_(None),
                FeatureToRepo.role == FeatureToRepoRole.PRIMARY,
            )
            .group_by(FeatureToRepo.repo_id)
        )
        result = await self._db.execute(stmt)
        return {row.repo_id: row.synth_count for row in result.all()}

    async def insert(
        self,
        *,
        feature_title: str,
        description: str,
        capabilities: dict[str, Any],
        cluster_names: list[str],
        tags: list[str] | None = None,
        embedding: list[float] | None = None,
    ) -> Feature:
        """Insert one immutable feature row.

        Repo binding lives on ``feature_to_repo``: the synth writer
        wrapper in :mod:`app.mcp.synth_feature_writer` does the feature
        insert + the PRIMARY junction insert in the same transaction.
        BACKEND junctions land later via :func:`replace_backend_links`.
        """
        assert self._org_id is not None, "org_id required for writes"
        row = Feature(
            org_id=self._org_id,
            feature_title=feature_title,
            description=description,
            capabilities=capabilities,
            cluster_names=cluster_names,
            tags=list(tags or []),
            embedding=embedding,
            synthesized_at=datetime.now(UTC),
        )
        self._db.add(row)
        await self._db.flush()
        await self._db.refresh(row)
        return row

    async def set_embedding(
        self,
        feature_id: uuid.UUID,
        embedding: list[float],
    ) -> None:
        """Lazy-fill ``embedding`` on a row that pre-dates the column."""
        await self._db.execute(
            sql_update(Feature)
            .where(
                Feature.org_id == self._org_id,
                Feature.id == feature_id,
            )
            .values(embedding=embedding)
        )

    async def list_active_grouped_by_repos(
        self, repo_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, list[Feature]]:
        """Active features for ``repo_ids`` keyed by their PRIMARY repo id.

        Joins through ``feature_to_repo`` on ``role='primary'`` to pick
        up the synthesis source repo per feature. Sorted by title within
        each repo for stable serialisation. Repos with zero current
        features are simply absent from the returned dict.
        """
        if not repo_ids:
            return {}
        result = await self._db.execute(
            self._scoped(
                select(Feature, FeatureToRepo.repo_id)
                .join(FeatureToRepo, FeatureToRepo.feature_id == Feature.id)
                .where(
                    Feature.superseded_at.is_(None),
                    FeatureToRepo.role == FeatureToRepoRole.PRIMARY,
                    FeatureToRepo.repo_id.in_(repo_ids),
                )
            ).order_by(FeatureToRepo.repo_id, Feature.feature_title)
        )
        grouped: dict[uuid.UUID, list[Feature]] = {}
        for feature, repo_id in result.all():
            grouped.setdefault(repo_id, []).append(feature)
        return grouped

    async def delete_for_primary_repo(self, repo_id: uuid.UUID) -> int:
        """Delete every feature whose PRIMARY junction points at ``repo_id``.

        Used by the synthesise stage's wipe-then-resynth flow: when a
        repo's SHA has changed (skip predicate returned no_skip), the
        existing feature set is wholesale-replaced rather than evolved
        through ``superseded_at`` markers. The cascade on
        ``feature_to_repo.feature_id`` removes both the PRIMARY junction
        and any BACKEND junctions that referred to those features in one
        statement. Returns the number of features deleted.

        Concurrency: the synthesise stage is per-repo and the scan
        runner serialises each repo's pipeline, so two wipes for the
        same ``(org_id, repo_id)`` cannot interleave. Cross-repo wipes
        running in parallel are independent because the WHERE clause
        scopes by ``repo_id``.
        """
        target_ids = (
            select(Feature.id)
            .join(FeatureToRepo, FeatureToRepo.feature_id == Feature.id)
            .where(
                Feature.org_id == self._org_id,
                FeatureToRepo.repo_id == repo_id,
                FeatureToRepo.role == FeatureToRepoRole.PRIMARY,
            )
            .scalar_subquery()
        )
        result = await self._db.execute(sql_delete(Feature).where(Feature.id.in_(target_ids)))
        # ``rowcount`` is well-defined for DELETE on asyncpg — but coerce
        # the negative-sentinel case (``-1`` when the driver couldn't
        # report) up to ``0`` so callers can rely on a non-negative count.
        return max(int(result.rowcount or 0), 0)

    async def supersede_prior_by_title(
        self,
        *,
        repo_id: uuid.UUID,
        feature_title: str,
    ) -> int:
        """Mark older rows for the same (PRIMARY repo, title) as superseded.

        Joins through ``feature_to_repo`` so we only supersede rows whose
        synthesis source matches the incoming repo. A feature linked to
        the same backend by route doesn't get superseded just because a
        new feature in another repo shares the same title.
        """
        now = datetime.now(UTC)
        # Subquery: ids of features whose PRIMARY junction row points at
        # the given repo and whose title matches.
        target_ids = (
            select(Feature.id)
            .join(FeatureToRepo, FeatureToRepo.feature_id == Feature.id)
            .where(
                Feature.org_id == self._org_id,
                Feature.feature_title == feature_title,
                Feature.superseded_at.is_(None),
                FeatureToRepo.repo_id == repo_id,
                FeatureToRepo.role == FeatureToRepoRole.PRIMARY,
            )
            .scalar_subquery()
        )
        result = await self._db.execute(
            sql_update(Feature).where(Feature.id.in_(target_ids)).values(superseded_at=now)
        )
        return result.rowcount

    async def get_by_id(self, feature_id: uuid.UUID) -> Feature | None:
        """Fetch a single row by primary key within org scope."""
        result = await self._db.execute(
            self._scoped(select(Feature).where(Feature.id == feature_id))
        )
        return result.scalar_one_or_none()

    async def find_current_by_title(self, feature_title: str) -> list[Feature]:
        """All current (non-superseded) rows for one feature title across the org."""
        result = await self._db.execute(
            self._scoped(
                select(Feature).where(
                    Feature.feature_title == feature_title,
                    Feature.superseded_at.is_(None),
                )
            ).order_by(Feature.synthesized_at.asc())
        )
        return list(result.scalars().all())

    async def list_current_for_repo(self, repo_id: uuid.UUID) -> list[Feature]:
        """List current rows whose PRIMARY junction row points at ``repo_id``."""
        result = await self._db.execute(
            self._scoped(
                select(Feature)
                .join(FeatureToRepo, FeatureToRepo.feature_id == Feature.id)
                .where(
                    FeatureToRepo.repo_id == repo_id,
                    FeatureToRepo.role == FeatureToRepoRole.PRIMARY,
                    Feature.superseded_at.is_(None),
                )
            ).order_by(Feature.synthesized_at.asc())
        )
        return list(result.scalars().all())

    async def list_current_for_org(self) -> list[Feature]:
        """Snapshot of all current pre-merge rows across the org."""
        result = await self._db.execute(
            self._scoped(select(Feature).where(Feature.superseded_at.is_(None))).order_by(
                Feature.synthesized_at.asc()
            )
        )
        return list(result.scalars().all())

    async def list_primary_pairs_for_repo(
        self, repo_id: uuid.UUID
    ) -> list[tuple[Feature, FeatureToRepo]]:
        """``(feature, primary_link)`` pairs for every current row in this repo.

        Used by the ``backend_link`` stage which needs both the feature
        row AND its PRIMARY junction's ``code_locations`` to drive the
        per-feature path extraction. Returning the pair from a single
        query avoids a second round-trip per feature.
        """
        result = await self._db.execute(
            self._scoped(
                select(Feature, FeatureToRepo)
                .join(FeatureToRepo, FeatureToRepo.feature_id == Feature.id)
                .where(
                    Feature.superseded_at.is_(None),
                    FeatureToRepo.repo_id == repo_id,
                    FeatureToRepo.role == FeatureToRepoRole.PRIMARY,
                )
            )
        )
        return list(result.all())

    async def cluster_names_for_repo(self, repo_id: uuid.UUID) -> set[str]:
        """Flat set of cluster names already synthesised under this repo.

        Powers the synthesis queue self-heal: diff the cluster list
        against this set to get the pending subset Claude still needs to
        process. PRIMARY-junction-scoped via JOIN.
        """
        result = await self._db.execute(
            self._scoped(
                select(Feature.cluster_names)
                .join(FeatureToRepo, FeatureToRepo.feature_id == Feature.id)
                .where(
                    FeatureToRepo.repo_id == repo_id,
                    FeatureToRepo.role == FeatureToRepoRole.PRIMARY,
                    Feature.superseded_at.is_(None),
                )
            )
        )
        names: set[str] = set()
        for (row_names,) in result.all():
            if row_names:
                names.update(row_names)
        return names
