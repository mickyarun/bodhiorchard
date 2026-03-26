"""Developer activity log repository."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dev_activity import DevActivityLog
from app.repositories.base import BaseRepository


class DevActivityLogRepository(BaseRepository[DevActivityLog]):
    """Repository for developer activity logs, scoped to an organization."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        """Initialize the repository."""
        super().__init__(DevActivityLog, db, org_id=org_id)

    async def list_for_bud(
        self, bud_id: uuid.UUID, *, limit: int = 100,
    ) -> list[DevActivityLog]:
        """List activity logs for a BUD, most recent first."""
        stmt = self._scoped(
            select(DevActivityLog)
            .where(DevActivityLog.bud_id == bud_id)
            .order_by(DevActivityLog.created_at.desc())
            .limit(limit)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())
