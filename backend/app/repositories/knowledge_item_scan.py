# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Scan-pipeline-specific queries against ``knowledge_items``.

Kept separate from ``knowledge_item.py`` so that the core KI repo
stays focused on CRUD / semantic search / dedupe and this module
holds the rollback-scoping concern: soft-delete scan-sourced features
scoped to the subset of repos whose HEAD SHA actually changed, so
unchanged repos never lose their features during a partial rebuild.

See ``BODHIORCHARD-ARCHITECTURE.md §18.12``.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy import update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge_item import KnowledgeItem, KnowledgeRepoLink

# Category + source pair that identifies scan-written feature rows.
# Exposed as module constants so the scan pipeline, rollback helper,
# and tests share one vocabulary instead of inlining string literals.
FEATURE_REGISTRY_CATEGORY = "feature_registry"
SCAN_SOURCE = "scan"


class KnowledgeItemScanRepository:
    """Scan-pipeline helpers that touch ``knowledge_items`` tables.

    Uses the same ``org_id``-scoping contract as ``BaseRepository`` but
    does not inherit from it — the methods here span ``KnowledgeItem``
    and ``KnowledgeRepoLink`` rather than targeting a single model class.
    """

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        """Initialise the repository.

        Args:
            db: Async SQLAlchemy session.
            org_id: Organization UUID used for scoping all queries.
        """
        self._db = db
        self._org_id = org_id

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
