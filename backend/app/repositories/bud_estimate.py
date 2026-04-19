# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Repository for BUD estimate snapshots and estimation-related queries."""

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bud import BUDDocument, BUDStatus
from app.models.bud_estimate_snapshot import BUDEstimateSnapshot
from app.repositories.base import BaseRepository

_TERMINAL_STATUSES = {BUDStatus.CLOSED, BUDStatus.DISCARDED, BUDStatus.PROD}


class BUDEstimateSnapshotRepository(BaseRepository[BUDEstimateSnapshot]):
    """Repository for estimate snapshots, scoped to an organization."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        """Initialize with async session and organization scope."""
        super().__init__(BUDEstimateSnapshot, db, org_id=org_id)

    async def list_for_bud(
        self,
        bud_id: uuid.UUID,
        *,
        limit: int = 20,
    ) -> list[BUDEstimateSnapshot]:
        """List estimation snapshots for a BUD, most recent first."""
        stmt = self._scoped(
            select(BUDEstimateSnapshot)
            .where(BUDEstimateSnapshot.bud_id == bud_id)
            .order_by(BUDEstimateSnapshot.created_at.desc())
            .limit(limit)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def get_latest_for_bud(
        self,
        bud_id: uuid.UUID,
    ) -> BUDEstimateSnapshot | None:
        """Get the most recent estimate snapshot for a BUD."""
        stmt = self._scoped(
            select(BUDEstimateSnapshot)
            .where(BUDEstimateSnapshot.bud_id == bud_id)
            .order_by(BUDEstimateSnapshot.created_at.desc())
            .limit(1)
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()


class BUDEstimateQueryRepository(BaseRepository[BUDDocument]):
    """Estimation-related queries on BUDDocument, scoped to an organization."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        """Initialize with async session and organization scope."""
        super().__init__(BUDDocument, db, org_id=org_id)

    async def count_active_in_phase(self, phase: str) -> int:
        """Count non-terminal BUDs currently in a given phase."""
        if phase in {s.value for s in _TERMINAL_STATUSES}:
            return 0
        stmt = self._scoped(
            select(func.count()).select_from(BUDDocument).where(BUDDocument.status == phase)
        )
        result = await self._db.execute(stmt)
        return result.scalar_one()

    async def count_ahead_in_queue(self, bud_number: int, phase: str) -> int:
        """Count BUDs with lower bud_number in the same or earlier phase."""
        phase_order = [s.value for s in BUDStatus if s not in _TERMINAL_STATUSES]
        try:
            phase_idx = phase_order.index(phase)
        except ValueError:
            return 0
        earlier_phases = phase_order[: phase_idx + 1]

        stmt = self._scoped(
            select(func.count())
            .select_from(BUDDocument)
            .where(
                BUDDocument.bud_number < bud_number,
                BUDDocument.status.in_(earlier_phases),
            )
        )
        result = await self._db.execute(stmt)
        return result.scalar_one()

    async def list_releasing_between(
        self,
        start_date: datetime,
        end_date: datetime,
    ) -> list[BUDDocument]:
        """List BUDs with prod_p70_date in the given date range (indexed)."""
        stmt = self._scoped(
            select(BUDDocument)
            .where(
                BUDDocument.prod_p70_date >= start_date,
                BUDDocument.prod_p70_date <= end_date,
            )
            .order_by(BUDDocument.prod_p70_date)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def list_overdue(self) -> list[BUDDocument]:
        """List BUDs whose current phase deadline has passed (indexed)."""
        stmt = self._scoped(
            select(BUDDocument)
            .where(
                BUDDocument.current_phase_deadline < func.now(),
                BUDDocument.status.notin_([s.value for s in _TERMINAL_STATUSES]),
            )
            .order_by(BUDDocument.current_phase_deadline)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())
