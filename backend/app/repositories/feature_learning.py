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

"""Repository for FeatureLearning rows (per-BUD post-close retrospective data).

Write owners:
- ``bud_metrics.compute_and_persist`` inserts / updates the structured
  ``metrics`` JSONB envelope.
- The Learning Agent result handler calls ``set_retrospective`` to fill
  in ``retrospective_md`` + ``embedding`` once the LLM completes.

Read consumers:
- The per-BUD Learnings tab via ``GET /v1/buds/{id}/learning``.
- The Learning Agent prompt builder (``find_similar`` for cross-BUD
  recap context).
- The org-level Learnings overview endpoint.

The estimator-feedback loop does NOT read this table directly — it
reads the precomputed ``velocity_aggregates`` rollup, which is kept in
sync by ``bud_metrics``. Keeping the estimator off the JSONB hot path
preserves O(1) read cost regardless of how many BUDs have closed.
"""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feature_learning import FeatureLearning
from app.repositories.base import BaseRepository


class FeatureLearningRepository(BaseRepository[FeatureLearning]):
    """Repository for per-BUD feature learning rows, scoped to an organization."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        """Initialize the repository."""
        super().__init__(FeatureLearning, db, org_id=org_id)

    async def get_for_bud(self, bud_id: uuid.UUID) -> FeatureLearning | None:
        """Return the single FeatureLearning row for a BUD, or None."""
        stmt = self._scoped(
            select(FeatureLearning).where(FeatureLearning.bud_id == bud_id).limit(1)
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert_for_bud(
        self,
        bud_id: uuid.UUID,
        *,
        cycle_time_days: float | None,
        estimated_days: float | None,
        bug_count: int,
        metrics: dict[str, Any] | None,
    ) -> FeatureLearning:
        """Insert or update the FeatureLearning row for this BUD.

        Caller is responsible for idempotency (skip-if-already-rich); this
        method always writes whatever it is given.
        """
        existing = await self.get_for_bud(bud_id)
        if existing is None:
            row = FeatureLearning(
                org_id=self._org_id,
                bud_id=bud_id,
                cycle_time_days=cycle_time_days,
                estimated_days=estimated_days,
                bug_count=bug_count,
                metrics=metrics,
            )
            self._db.add(row)
            await self._db.flush()
            await self._db.refresh(row)
            return row

        existing.cycle_time_days = cycle_time_days
        existing.estimated_days = estimated_days
        existing.bug_count = bug_count
        existing.metrics = metrics
        await self._db.flush()
        await self._db.refresh(existing)
        return existing

    async def set_retrospective(
        self,
        bud_id: uuid.UUID,
        *,
        retrospective_md: str,
        embedding: list[float] | None,
    ) -> FeatureLearning | None:
        """Attach the LLM-generated recap + embedding to an existing row."""
        row = await self.get_for_bud(bud_id)
        if row is None:
            return None
        row.retrospective_md = retrospective_md
        if embedding is not None:
            row.embedding = embedding
        await self._db.flush()
        await self._db.refresh(row)
        return row

    async def find_similar(
        self,
        embedding: list[float],
        *,
        limit: int = 3,
        exclude_bud_id: uuid.UUID | None = None,
    ) -> list[FeatureLearning]:
        """Return up to ``limit`` prior recaps by ascending cosine distance.

        Used by the Learning Agent prompt builder to seed cross-BUD
        context ("design phase has dragged on the last similar BUDs").
        Caller decides whether to use the rows — distance filtering can
        be reintroduced here once the org-overview UI surfaces "how
        similar" data and we know the right threshold from real usage.
        """
        stmt = self._scoped(
            select(FeatureLearning)
            .where(
                FeatureLearning.embedding.is_not(None),
                FeatureLearning.retrospective_md.is_not(None),
            )
            .order_by(FeatureLearning.embedding.cosine_distance(embedding))
            .limit(limit)
        )
        if exclude_bud_id is not None:
            stmt = stmt.where(FeatureLearning.bud_id != exclude_bud_id)
        result = await self._db.execute(stmt)
        return list(result.scalars().all())
