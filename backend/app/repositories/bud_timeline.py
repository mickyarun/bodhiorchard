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

"""Timeline event data access repository for BUD documents."""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bud import BUDDocument, BUDTimelineEvent
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

    async def list_for_bud_by_event_type(
        self, bud_id: uuid.UUID, event_type: str
    ) -> list[BUDTimelineEvent]:
        """Every event for a BUD matching a single event_type."""
        stmt = self._scoped(
            select(BUDTimelineEvent).where(
                BUDTimelineEvent.bud_id == bud_id,
                BUDTimelineEvent.event_type == event_type,
            )
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def list_status_changes_with_bud_in_window(
        self, since: datetime, until: datetime
    ) -> list[tuple[uuid.UUID, int, str | None, dict | None]]:
        """``status_change`` events in [since, until) joined with BUD info.

        Returns ``(actor_id, bud_number, bud_title, detail)`` tuples for
        every event whose ``actor_id`` is set. The standup service
        groups these per-actor for the daily transitions list.
        """
        stmt = self._scoped(
            select(
                BUDTimelineEvent.actor_id,
                BUDDocument.bud_number,
                BUDDocument.title,
                BUDTimelineEvent.detail,
            )
            .join(BUDDocument, BUDTimelineEvent.bud_id == BUDDocument.id)
            .where(
                BUDTimelineEvent.event_type == "status_change",
                BUDTimelineEvent.created_at >= since,
                BUDTimelineEvent.created_at < until,
                BUDTimelineEvent.actor_id.isnot(None),
            )
        )
        result = await self._db.execute(stmt)
        return [(row.actor_id, row.bud_number, row.title, row.detail) for row in result.all()]

    async def list_for_bud_by_event_types(
        self, bud_id: uuid.UUID, event_types: list[str]
    ) -> list[BUDTimelineEvent]:
        """All events for a BUD matching any of the given event types, chronological."""
        stmt = self._scoped(
            select(BUDTimelineEvent)
            .where(
                BUDTimelineEvent.bud_id == bud_id,
                BUDTimelineEvent.event_type.in_(event_types),
            )
            .order_by(BUDTimelineEvent.created_at.asc())
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())
