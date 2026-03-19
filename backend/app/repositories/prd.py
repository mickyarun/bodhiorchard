"""PRD document data access repository."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.prd import PRDDocument
from app.repositories.base import BaseRepository


class PRDRepository(BaseRepository[PRDDocument]):
    """Repository for PRDDocument queries, scoped to an organization."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        """Initialize the repository.

        Args:
            db: Async SQLAlchemy session.
            org_id: Organization UUID for scoping queries.
        """
        super().__init__(PRDDocument, db, org_id=org_id)

    async def list_prds(
        self,
        *,
        status_filter: str | None = None,
        limit: int | None = None,
    ) -> list[PRDDocument]:
        """List PRDs ordered by prd_number descending.

        Args:
            status_filter: Optional status string to filter by.
            limit: Maximum number of results.

        Returns:
            List of PRDDocument instances.
        """
        stmt = self._scoped(select(PRDDocument).order_by(PRDDocument.prd_number.desc()))
        if status_filter:
            stmt = stmt.where(PRDDocument.status == status_filter)
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def next_prd_number(self) -> int:
        """Get the next auto-incremented PRD number for the organization.

        Returns:
            The next available PRD number (max + 1, or 1 if none exist).
        """
        result = await self._db.execute(
            select(func.coalesce(func.max(PRDDocument.prd_number), 0)).where(
                PRDDocument.org_id == self._org_id
            )
        )
        return result.scalar_one() + 1
