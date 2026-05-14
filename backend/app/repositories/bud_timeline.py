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
from typing import Any

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
    ) -> list[tuple[uuid.UUID, int, str | None, dict[str, Any] | None]]:
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

    async def latest_assignee_for_roles(
        self, bud_id: uuid.UUID, role_values: list[str]
    ) -> tuple[uuid.UUID, datetime, str] | None:
        """Return the most recent ``assigned`` event whose ``detail.role`` matches.

        Used for continuity on phase re-entry — when a BUD comes back to
        a phase, prefer the previous assignee whose role belongs to the
        new phase's chain. Returns ``(assignee_id, created_at, role)``
        so callers can compare against any later ``unassigned`` event.
        Returns ``None`` when no matching event exists.
        """
        if not role_values:
            return None
        stmt = self._scoped(
            select(
                BUDTimelineEvent.detail["assignee_id"].astext,
                BUDTimelineEvent.created_at,
                BUDTimelineEvent.detail["role"].astext,
            )
            .where(
                BUDTimelineEvent.bud_id == bud_id,
                BUDTimelineEvent.event_type == "assigned",
                BUDTimelineEvent.detail["role"].astext.in_(role_values),
                BUDTimelineEvent.detail["assignee_id"].astext.isnot(None),
            )
            .order_by(BUDTimelineEvent.created_at.desc())
            .limit(1)
        )
        result = await self._db.execute(stmt)
        row = result.first()
        if row is None or row[0] is None:
            return None
        try:
            return (uuid.UUID(row[0]), row[1], row[2])
        except ValueError:
            return None

    # System-emitted unassign reasons. A user-triggered unassign has
    # neither of these (or any other value the human picks up on) — so we
    # treat anything outside this set as a deliberate "don't bring them
    # back" signal that suppresses continuity.
    _SYSTEM_UNASSIGN_REASONS: frozenset[str] = frozenset({"auto_assign_skipped", "reassigned"})

    async def latest_user_unassign_after(self, bud_id: uuid.UUID, since: datetime) -> bool:
        """Return ``True`` if a user-triggered ``unassigned`` event exists after ``since``.

        System unassigns are stamped with ``detail.reason`` (see
        :data:`_SYSTEM_UNASSIGN_REASONS`); anything else is treated as a
        human action.
        """
        stmt = self._scoped(
            select(BUDTimelineEvent.detail)
            .where(
                BUDTimelineEvent.bud_id == bud_id,
                BUDTimelineEvent.event_type == "unassigned",
                BUDTimelineEvent.created_at > since,
            )
            .order_by(BUDTimelineEvent.created_at.desc())
        )
        result = await self._db.execute(stmt)
        for (detail,) in result.all():
            reason = (detail or {}).get("reason")
            if reason not in self._SYSTEM_UNASSIGN_REASONS:
                return True
        return False
