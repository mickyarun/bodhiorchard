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

    async def first_status_change_to(
        self, bud_id: uuid.UUID, to_status: str
    ) -> tuple[uuid.UUID | None, datetime] | None:
        """Earliest ``status_change`` into ``to_status`` → ``(actor_id, created_at)``.

        Answers "who first moved this BUD into <stage>, and when?" — the
        signal behind the PM requirement→design credit (actor) and the
        tech-arch / on-time timing rules (timestamp). ``actor_id`` may be
        ``None`` for system-driven (auto) transitions. Returns ``None`` when
        the BUD never entered that stage.

        ``to_status`` must be the ``BUDStatus`` *value* (e.g.
        ``BUDStatus.DEVELOPMENT.value`` → ``"development"``), matching the
        ``detail["to"]`` string written by the status-change recorder — not
        the enum member or its ``.name``.
        """
        stmt = self._scoped(
            select(BUDTimelineEvent.actor_id, BUDTimelineEvent.created_at)
            .where(
                BUDTimelineEvent.bud_id == bud_id,
                BUDTimelineEvent.event_type == "status_change",
                BUDTimelineEvent.detail["to"].astext == to_status,
            )
            .order_by(BUDTimelineEvent.created_at.asc())
            .limit(1)
        )
        result = await self._db.execute(stmt)
        row = result.first()
        if row is None:
            return None
        return (row[0], row[1])

    async def distinct_actors_for_event(
        self, bud_id: uuid.UUID, event_type: str
    ) -> set[uuid.UUID]:
        """Distinct non-null ``actor_id`` across a BUD's events of one type.

        Backs the designer "design contribution" credit: the set of people who
        emitted a ``design_updated`` event (figma link / MCP / AI chat).
        """
        stmt = self._scoped(
            select(BUDTimelineEvent.actor_id).where(
                BUDTimelineEvent.bud_id == bud_id,
                BUDTimelineEvent.event_type == event_type,
                BUDTimelineEvent.actor_id.is_not(None),
            )
        ).distinct()
        result = await self._db.execute(stmt)
        return {row[0] for row in result.all() if row[0] is not None}

    async def has_qa_skip_override(self, bud_id: uuid.UUID) -> bool:
        """True if QA left testing having skipped/overridden a manual test case.

        Matches the ``status_override`` event tagged ``detail.kind == "qa_skip"``
        (recorded by the testing→uat transition). Used by the QA "tests not
        skipped/overridden" SP rule to drop the full credit to the reduced one.
        """
        stmt = self._scoped(
            select(BUDTimelineEvent.id)
            .where(
                BUDTimelineEvent.bud_id == bud_id,
                BUDTimelineEvent.event_type == "status_override",
                BUDTimelineEvent.detail["kind"].astext == "qa_skip",
            )
            .limit(1)
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def latest_assignee_for_phase(
        self, bud_id: uuid.UUID, phase_value: str
    ) -> tuple[uuid.UUID, datetime, str | None] | None:
        """Return the most recent ``assigned`` event whose ``detail.phase`` matches.

        Used for continuity on phase re-entry — when a BUD comes back to
        a phase, prefer the assignee who held it the last time the BUD
        was actually in this phase. Matching on ``detail.phase`` (rather
        than ``detail.role`` against the chain) stops cross-phase bleed:
        a PM assigned during the ``bud`` phase no longer wins continuity
        on first entry to ``design`` just because PM is the design
        chain's fallback role.

        Returns ``(assignee_id, created_at, role)`` — ``role`` is ``None``
        for legacy events that didn't record one. ``None`` when no
        matching event exists (including pre-deploy events that lack the
        ``phase`` key; those degrade to the chain walk, which is the
        intended fallback).
        """
        stmt = self._scoped(
            select(
                BUDTimelineEvent.detail["assignee_id"].astext,
                BUDTimelineEvent.created_at,
                BUDTimelineEvent.detail["role"].astext,
            )
            .where(
                BUDTimelineEvent.bud_id == bud_id,
                BUDTimelineEvent.event_type == "assigned",
                BUDTimelineEvent.detail["phase"].astext == phase_value,
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
