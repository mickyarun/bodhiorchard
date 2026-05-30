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

"""Repository for ``velocity_aggregates`` — the estimator's hot-path rollup.

One row per ``(org_id, complexity, phase)`` keeps the rolling actuals
window, percentiles, PERT triple, and Welford running statistics.
Writes are driven by ``velocity_aggregate_writer`` after each BUD
close; reads are driven by ``estimation_context`` on every estimation.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bud import BUDStatus
from app.models.velocity_aggregate import VelocityAggregate
from app.repositories.base import BaseRepository


class VelocityAggregateRepository(BaseRepository[VelocityAggregate]):
    """Repository for velocity aggregates, scoped to an organization."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        """Initialize the repository."""
        super().__init__(VelocityAggregate, db, org_id=org_id)

    async def get_bucket(
        self,
        complexity: int,
        phase: BUDStatus,
    ) -> VelocityAggregate | None:
        """Fetch the single bucket row for ``(complexity, phase)``."""
        stmt = self._scoped(
            select(VelocityAggregate)
            .where(
                VelocityAggregate.complexity == complexity,
                VelocityAggregate.phase == phase,
            )
            .limit(1)
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_complexity_range(
        self,
        low: int,
        high: int,
        phases: list[BUDStatus],
    ) -> list[VelocityAggregate]:
        """All bucket rows in ``[low, high]`` for the requested phases.

        Single indexed scan — used by the estimator's hot-path read so
        a per-org estimation pulls at most ``(high - low + 1) * len(phases)``
        rows (~40 in the worst case, typically far fewer).
        """
        if not phases or low > high:
            return []
        stmt = self._scoped(
            select(VelocityAggregate).where(
                VelocityAggregate.complexity >= low,
                VelocityAggregate.complexity <= high,
                VelocityAggregate.phase.in_(phases),
            )
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def upsert_bucket_state(
        self,
        complexity: int,
        phase: BUDStatus,
        *,
        sample_window: list[float],
        contributing_bud_ids: list[str],
        n_samples: int,
        running_mean: float,
        running_m2: float,
        p50_days: float,
        p70_days: float,
        p85_days: float,
        pert_optimistic: float,
        pert_most_likely: float,
        pert_pessimistic: float,
    ) -> VelocityAggregate:
        """Insert or update the bucket row with a freshly-computed snapshot.

        Caller owns the math (Welford update, percentile re-derivation);
        this method just persists the result so the SQL stays in the
        repository layer per the project's "SQL only in repositories"
        rule.
        """
        row = await self.get_bucket(complexity, phase)
        if row is None:
            row = VelocityAggregate(
                org_id=self._org_id,
                complexity=complexity,
                phase=phase,
            )
            self._db.add(row)
        row.sample_window = sample_window
        row.contributing_bud_ids = contributing_bud_ids
        row.n_samples = n_samples
        row.running_mean = running_mean
        row.running_m2 = running_m2
        row.p50_days = p50_days
        row.p70_days = p70_days
        row.p85_days = p85_days
        row.pert_optimistic = pert_optimistic
        row.pert_most_likely = pert_most_likely
        row.pert_pessimistic = pert_pessimistic
        await self._db.flush()
        await self._db.refresh(row)
        return row

    async def list_buckets_due_for_30d_snapshot(
        self,
        *,
        now: datetime | None = None,
        threshold_seconds: int = 86_400,
    ) -> list[VelocityAggregate]:
        """Buckets whose 30-day snapshot is missing or older than a day.

        Driven by the daily snapshot-roller job. Restricts to the
        repository's scoped org so each org's snapshot work is bounded.
        """
        cutoff = (now or datetime.now(tz=UTC)).timestamp() - threshold_seconds
        # snapshot_taken_at NULL → never rolled; otherwise compare timestamps
        stmt = self._scoped(
            select(VelocityAggregate).where(
                (VelocityAggregate.snapshot_taken_at.is_(None))
                | (VelocityAggregate.snapshot_taken_at < datetime.fromtimestamp(cutoff))
            )
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def write_30d_snapshot(
        self,
        bucket_id: uuid.UUID,
        running_mean_30d_ago: float | None,
        snapshot_taken_at: datetime,
    ) -> None:
        """Advance the 30-day baseline snapshot for one bucket.

        Tenant-scoped: a caller holding org A's repo cannot mutate a
        bucket belonging to org B even if it somehow obtained that
        bucket's id. The single ``_scoped`` select enforces the
        ``org_id == self._org_id`` predicate before the row is loaded.
        """
        stmt = self._scoped(
            select(VelocityAggregate).where(VelocityAggregate.id == bucket_id).limit(1)
        )
        result = await self._db.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            return
        row.running_mean_30d_ago = running_mean_30d_ago
        row.snapshot_taken_at = snapshot_taken_at
        await self._db.flush()
