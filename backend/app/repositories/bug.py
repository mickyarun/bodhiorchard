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

"""Bug data access repository."""

import uuid
from datetime import datetime

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bug import Bug, BugSeverity, BugStatus
from app.repositories.base import BaseRepository


class BugRepository(BaseRepository[Bug]):
    """Repository for Bug queries, scoped to an organization."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        super().__init__(Bug, db, org_id=org_id)

    async def count_open_for_bud_with_statuses(
        self, bud_id: uuid.UUID, statuses: tuple[BugStatus, ...]
    ) -> int:
        """Count bugs for a BUD whose status is in the given set."""
        stmt = self._scoped(
            select(func.count())
            .select_from(Bug)
            .where(
                Bug.bud_id == bud_id,
                Bug.status.in_(statuses),
            )
        )
        result = await self._db.execute(stmt)
        return result.scalar_one()

    async def list_recent_open(self, limit: int = 20) -> list[Bug]:
        """Most-recent open / in-progress / blocked bugs, newest first."""
        stmt = self._scoped(
            select(Bug)
            .where(Bug.status.in_([BugStatus.OPEN, BugStatus.IN_PROGRESS, BugStatus.BLOCKED]))
            .order_by(Bug.created_at.desc())
            .limit(limit)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def count_filed_by_reporter_in_window(
        self, since: datetime, until: datetime
    ) -> dict[uuid.UUID, int]:
        """Count bugs filed per reporter with ``created_at`` in [since, until)."""
        stmt = self._scoped(
            select(Bug.reporter_id, func.count().label("cnt"))
            .where(
                Bug.created_at >= since,
                Bug.created_at < until,
                Bug.reporter_id.isnot(None),
            )
            .group_by(Bug.reporter_id)
        )
        result = await self._db.execute(stmt)
        return {row.reporter_id: row.cnt for row in result.all()}

    async def count_resolved_by_assignee_in_window(
        self, since: datetime, until: datetime
    ) -> dict[uuid.UUID, int]:
        """Count bugs resolved per assignee with ``resolved_at`` in [since, until)."""
        stmt = self._scoped(
            select(Bug.assignee_id, func.count().label("cnt"))
            .where(
                Bug.resolved_at >= since,
                Bug.resolved_at < until,
                Bug.assignee_id.isnot(None),
            )
            .group_by(Bug.assignee_id)
        )
        result = await self._db.execute(stmt)
        return {row.assignee_id: row.cnt for row in result.all()}

    async def count_critical_open(self) -> int:
        """Count bugs with severity=critical and status in (open, in_progress)."""
        stmt = self._scoped(
            select(func.count()).where(
                Bug.severity == BugSeverity.CRITICAL,
                Bug.status.in_([BugStatus.OPEN, BugStatus.IN_PROGRESS]),
            )
        )
        result = await self._db.execute(stmt)
        return result.scalar() or 0

    async def open_bug_counts_by_bud(self, bud_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
        """Count open bugs (open / in_progress / blocked) per BUD id.

        Args:
            bud_ids: BUD UUIDs to fetch counts for.

        Returns:
            Mapping of bud_id -> open bug count. BUDs with zero open bugs
            are absent from the dict.
        """
        if not bud_ids:
            return {}
        stmt = self._scoped(
            select(Bug.bud_id, func.count(Bug.id))
            .where(
                Bug.bud_id.in_(bud_ids),
                Bug.status.in_([BugStatus.OPEN, BugStatus.IN_PROGRESS, BugStatus.BLOCKED]),
            )
            .group_by(Bug.bud_id)
        )
        result = await self._db.execute(stmt)
        return {row[0]: row[1] for row in result.all() if row[0] is not None}

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
            select(Bug).where(Bug.bud_id == bud_id).order_by(Bug.created_at.desc()),
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
        stmt: Select[tuple[Bug]],
        *,
        status: str | None = None,
        severity: str | None = None,
        bud_id: uuid.UUID | None = None,
    ) -> Select[tuple[Bug]]:
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
