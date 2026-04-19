# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Timeline event data access repository for BUD documents."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bud import BUDTimelineEvent
from app.repositories.base import BaseRepository


class BUDTimelineRepository(BaseRepository[BUDTimelineEvent]):
    """Repository for BUD timeline events, scoped by org_id."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        super().__init__(BUDTimelineEvent, db, org_id=org_id)

    async def list_for_bud(self, bud_id: uuid.UUID) -> list[BUDTimelineEvent]:
        """All events for a BUD, chronological order."""
        stmt = self._scoped(
            select(BUDTimelineEvent)
            .where(BUDTimelineEvent.bud_id == bud_id)
            .order_by(BUDTimelineEvent.created_at.asc())
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())
