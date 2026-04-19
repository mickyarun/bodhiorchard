# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Bug data access repository."""

import uuid

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bug import Bug, BugStatus
from app.repositories.base import BaseRepository


class BugRepository(BaseRepository[Bug]):
    """Repository for Bug queries, scoped to an organization."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        super().__init__(Bug, db, org_id=org_id)

    async def list_filtered(
        self,
        *,
        status: str | None = None,
        severity: str | None = None,
        bud_id: uuid.UUID | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Bug], int]:
        """Paginated bug list with optional filters.

        Returns (items, total_count) tuple for the paginated response.
        """
        base = self._scoped(select(Bug))
        base = self._apply_filters(base, status=status, severity=severity, bud_id=bud_id)

        # Total count (same filters, no pagination)
        count_stmt = select(func.count()).select_from(base.subquery())
        total = (await self._db.execute(count_stmt)).scalar() or 0

        # Paginated results
        stmt = base.order_by(Bug.created_at.desc())
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)
        result = await self._db.execute(stmt)
        return list(result.scalars().all()), total

    async def list_for_bud(self, bud_id: uuid.UUID) -> list[Bug]:
        """All bugs linked to a specific BUD, newest first."""
        stmt = self._scoped(
            select(Bug)
            .where(Bug.bud_id == bud_id)
            .order_by(Bug.created_at.desc()),
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def count_for_bud(self, bud_id: uuid.UUID) -> int:
        """Count bugs linked to a specific BUD."""
        stmt = self._scoped(
            select(func.count(Bug.id)).where(Bug.bud_id == bud_id),
        )
        result = await self._db.execute(stmt)
        return result.scalar() or 0

    async def count_open_for_bud(self, bud_id: uuid.UUID) -> int:
        """Count open (unresolved) bugs linked to a specific BUD.

        Includes: open, in-progress, blocked. Excludes: resolved, closed.
        """
        stmt = self._scoped(
            select(func.count(Bug.id)).where(
                Bug.bud_id == bud_id,
                Bug.status.in_([BugStatus.OPEN, BugStatus.IN_PROGRESS, BugStatus.BLOCKED]),
            ),
        )
        result = await self._db.execute(stmt)
        return result.scalar() or 0

    async def search_by_status(
        self,
        *,
        status_filter: str = "open",
        limit: int = 10,
    ) -> list[Bug]:
        """Search bugs by status with recent-first ordering.

        Args:
            status_filter: Comma-separated statuses or single status.
                Use ``"open"`` for default open statuses, ``"all"`` for no filter.
            limit: Maximum number of results.

        Returns:
            List of Bug instances matching the filter.
        """
        stmt = self._scoped(select(Bug))
        if status_filter == "open":
            stmt = stmt.where(
                Bug.status.in_([BugStatus.OPEN, BugStatus.IN_PROGRESS, BugStatus.BLOCKED]),
            )
        elif status_filter != "all":
            statuses = [s.strip().lower() for s in status_filter.split(",")]
            stmt = stmt.where(Bug.status.in_(statuses))
        stmt = stmt.order_by(Bug.created_at.desc()).limit(limit)
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    def _apply_filters(
        stmt: Select[tuple[Bug, ...]],
        *,
        status: str | None = None,
        severity: str | None = None,
        bud_id: uuid.UUID | None = None,
    ) -> Select[tuple[Bug, ...]]:
        """Apply optional filters to a Bug query."""
        if status:
            statuses = [s.strip().lower() for s in status.split(",")]
            stmt = stmt.where(Bug.status.in_(statuses))
        if severity:
            severities = [s.strip().lower() for s in severity.split(",")]
            stmt = stmt.where(Bug.severity.in_(severities))
        if bud_id:
            stmt = stmt.where(Bug.bud_id == bud_id)
        return stmt
