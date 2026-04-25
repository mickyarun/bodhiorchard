# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Scan-pipeline-specific queries against ``knowledge_items``.

Kept separate from ``knowledge_item.py`` so that the core KI repo
stays focused on CRUD / semantic search / dedupe and this module
holds the three scan-only concerns:

- Audit: find KIs that should have a ``knowledge_to_repo`` link but
  don't (the silent-orphan symptom from §18.12).
- Repair: bulk-insert missing ``knowledge_to_repo`` rows.
- Rollback scoping: soft-delete scan-sourced features scoped to the
  subset of repos whose HEAD SHA actually changed, so unchanged repos
  never lose their features during a partial rebuild.

See ``BODHIORCHARD-ARCHITECTURE.md §18.12``.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy import update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge_item import KnowledgeItem, KnowledgeRepoLink
from app.models.synthesized_feature import SynthesizedFeature

# Category + source pair that identifies scan-written feature rows.
# Exposed as module constants so the scan pipeline, rollback helper,
# and tests share one vocabulary instead of inlining string literals.
FEATURE_REGISTRY_CATEGORY = "feature_registry"
SCAN_SOURCE = "scan"


class KnowledgeItemScanRepository:
    """Scan-pipeline helpers that touch ``knowledge_items`` tables.

    Uses the same ``org_id``-scoping contract as ``BaseRepository`` but
    does not inherit from it — the methods here do not target a single
    model class; they span ``KnowledgeItem``, ``KnowledgeRepoLink``,
    and ``SynthesizedFeature``.
    """

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        """Initialise the repository.

        Args:
            db: Async SQLAlchemy session.
            org_id: Organization UUID used for scoping all queries.
        """
        self._db = db
        self._org_id = org_id

    # --- Audit ---------------------------------------------------------

    async def find_items_missing_repo_link(self, repo_id: uuid.UUID) -> list[uuid.UUID]:
        """Return KI ids that should be linked to ``repo_id`` but aren't.

        A "should be linked" row is one where ``synthesized_features``
        has a row with that ``knowledge_item_id`` + ``repo_id`` (the
        ground-truth pre-merge record) but ``knowledge_to_repo`` has no
        matching junction row for the same pair.

        Returns:
            Deduplicated list of ``knowledge_item_id`` values.
        """
        stmt = (
            select(SynthesizedFeature.knowledge_item_id)
            .outerjoin(
                KnowledgeRepoLink,
                (KnowledgeRepoLink.knowledge_id == SynthesizedFeature.knowledge_item_id)
                & (KnowledgeRepoLink.repo_id == repo_id),
            )
            .where(
                SynthesizedFeature.org_id == self._org_id,
                SynthesizedFeature.repo_id == repo_id,
                SynthesizedFeature.knowledge_item_id.is_not(None),
                SynthesizedFeature.superseded_at.is_(None),
                KnowledgeRepoLink.id.is_(None),
            )
            .distinct()
        )
        result = await self._db.execute(stmt)
        return [row[0] for row in result.all() if row[0] is not None]

    # --- Repair --------------------------------------------------------

    async def insert_missing_links(
        self,
        knowledge_item_ids: list[uuid.UUID],
        *,
        repo_id: uuid.UUID,
    ) -> list[uuid.UUID]:
        """Insert ``knowledge_to_repo`` rows for pairs that don't exist yet.

        Safe to call with a superset of missing IDs: any ``(knowledge_id,
        repo_id)`` pair that already has a junction row is filtered out
        first, so the insert only creates net-new rows.

        Returns:
            The subset of ids for which a new junction row was inserted.
        """
        if not knowledge_item_ids:
            return []
        existing_stmt = select(KnowledgeRepoLink.knowledge_id).where(
            KnowledgeRepoLink.repo_id == repo_id,
            KnowledgeRepoLink.knowledge_id.in_(knowledge_item_ids),
        )
        existing_rows = await self._db.execute(existing_stmt)
        existing = {row[0] for row in existing_rows.all()}

        to_insert = [k for k in knowledge_item_ids if k not in existing]
        for kid in to_insert:
            self._db.add(KnowledgeRepoLink(knowledge_id=kid, repo_id=repo_id))
        if to_insert:
            await self._db.flush()
        return to_insert

    # --- Rollback scoping ----------------------------------------------

    async def soft_delete_by_repo_ids(
        self,
        repo_ids: list[uuid.UUID],
        *,
        category: str = FEATURE_REGISTRY_CATEGORY,
        source: str = SCAN_SOURCE,
    ) -> list[uuid.UUID]:
        """Soft-delete scan-sourced items linked to any of these repos.

        Called at scan start when ``D.7``-scoped cleanup runs: we only
        dirty the feature set for repos whose SHA actually changed,
        leaving unchanged repos untouched. The returned IDs are stashed
        for the failure-rollback path (see ``_rollback_soft_deleted_features``
        in ``scan_pipeline.py``) so a crashed scan reactivates only
        what it deactivated.

        Args:
            repo_ids: Tracked-repository UUIDs whose scan-sourced
                feature rows should be soft-deleted.
            category: Knowledge category to target. Defaults to
                ``feature_registry`` — the only scan-written category
                today.
            source: ``source`` column value to target. Defaults to
                ``scan`` so BUD-authored features are never touched.

        Returns:
            IDs that were deactivated, in insertion order.
        """
        if not repo_ids:
            return []
        id_stmt = (
            select(KnowledgeItem.id)
            .join(
                KnowledgeRepoLink,
                KnowledgeRepoLink.knowledge_id == KnowledgeItem.id,
            )
            .where(
                KnowledgeItem.org_id == self._org_id,
                KnowledgeItem.category == category,
                KnowledgeItem.source == source,
                KnowledgeItem.is_active.is_(True),
                KnowledgeRepoLink.repo_id.in_(repo_ids),
            )
            .distinct()
        )
        id_rows = await self._db.execute(id_stmt)
        ids = [row[0] for row in id_rows.all()]
        if not ids:
            return []
        await self._db.execute(
            sql_update(KnowledgeItem).where(KnowledgeItem.id.in_(ids)).values(is_active=False)
        )
        return ids
