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

"""Scan-pipeline-specific queries against ``features``.

Kept separate from ``feature.py`` so the core repository stays focused
on CRUD / semantic search / reconciler reads, while this module owns
the rollback-scoping concern: soft-delete scan-sourced features
limited to the subset of repos whose HEAD SHA actually changed, so
unchanged repos never lose their features during a partial rebuild.

Mirrors the contract of the retired ``knowledge_item_scan`` module
(soft_delete_by_repo_ids), but operates on ``Feature.is_active`` and
joins through ``feature_to_repo`` PRIMARY rows instead of the legacy
``knowledge_to_repo`` junction.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy import update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feature import Feature
from app.models.feature_to_repo import FeatureToRepo, FeatureToRepoRole

SCAN_SOURCE = "scan"


class FeatureScanRepository:
    """Scan-pipeline helpers that touch the ``features`` table.

    Uses the same ``org_id``-scoping contract as ``BaseRepository`` but
    does not inherit from it — the methods here span ``Feature`` and
    ``FeatureToRepo`` rather than targeting a single model class.
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
        source: str = SCAN_SOURCE,
    ) -> list[uuid.UUID]:
        """Soft-delete scan-sourced features linked to any of these repos.

        Called by the reconciler's pre-run rollback hook in
        :mod:`app.scan.soft_delete`: we only dirty the feature set for
        repos whose SHA actually changed, leaving unchanged repos
        untouched. The returned IDs are stashed for the failure-rollback
        path so a crashed scan reactivates only what it deactivated.

        Filters by ``source='scan'`` so BUD-authored features
        (``source='bud'``) are never touched by a scan run.

        Args:
            repo_ids: Tracked-repository UUIDs whose scan-sourced
                feature rows should be soft-deleted.
            source: ``source`` column value to target. Defaults to
                ``'scan'``.

        Returns:
            IDs that were deactivated, in PRIMARY-junction order.
        """
        if not repo_ids:
            return []
        id_stmt = (
            select(Feature.id)
            .join(FeatureToRepo, FeatureToRepo.feature_id == Feature.id)
            .where(
                Feature.org_id == self._org_id,
                Feature.source == source,
                Feature.is_active.is_(True),
                FeatureToRepo.role == FeatureToRepoRole.PRIMARY,
                FeatureToRepo.repo_id.in_(repo_ids),
            )
            .distinct()
        )
        id_rows = await self._db.execute(id_stmt)
        ids = [row[0] for row in id_rows.all()]
        if not ids:
            return []
        await self._db.execute(
            sql_update(Feature)
            .where(Feature.id.in_(ids))
            .values(is_active=False, deactivated_at=datetime.now(UTC))
        )
        return ids

    async def reactivate_by_ids(self, feature_ids: list[uuid.UUID]) -> int:
        """Re-activate features previously soft-deleted by this repo.

        Counterpart used by the reconciler's failure-rollback. Only
        flips rows whose ``is_active`` is currently ``False`` so
        re-running rollback after partial recovery is safe.

        Returns the number of rows touched.
        """
        if not feature_ids:
            return 0
        result = await self._db.execute(
            sql_update(Feature)
            .where(
                Feature.org_id == self._org_id,
                Feature.id.in_(feature_ids),
                Feature.is_active.is_(False),
            )
            .values(is_active=True, deactivated_at=None)
        )
        return max(int(getattr(result, "rowcount", 0) or 0), 0)
