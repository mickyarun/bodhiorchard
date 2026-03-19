"""Bug data access repository."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bug import Bug
from app.repositories.base import BaseRepository


class BugRepository(BaseRepository[Bug]):
    """Repository for Bug queries, scoped to an organization."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        """Initialize the repository.

        Args:
            db: Async SQLAlchemy session.
            org_id: Organization UUID for scoping queries.
        """
        super().__init__(Bug, db, org_id=org_id)

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
            stmt = stmt.where(Bug.status.in_(["OPEN", "IN_PROGRESS", "IN-PROGRESS", "BLOCKED"]))
        elif status_filter != "all":
            statuses = [s.strip().upper() for s in status_filter.split(",")]
            stmt = stmt.where(Bug.status.in_(statuses))
        stmt = stmt.order_by(Bug.created_at.desc()).limit(limit)
        result = await self._db.execute(stmt)
        return list(result.scalars().all())
