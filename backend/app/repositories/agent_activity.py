# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Agent activity log repository."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_activity import AgentActivityLog
from app.repositories.base import BaseRepository


class AgentActivityLogRepository(BaseRepository[AgentActivityLog]):
    """Repository for agent activity logs, scoped to an organization."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        """Initialize the repository."""
        super().__init__(AgentActivityLog, db, org_id=org_id)

    async def list_for_bud(
        self,
        bud_id: uuid.UUID,
        *,
        limit: int = 100,
    ) -> list[AgentActivityLog]:
        """List agent activity logs for a BUD, most recent first."""
        stmt = self._scoped(
            select(AgentActivityLog)
            .where(AgentActivityLog.bud_id == bud_id)
            .order_by(AgentActivityLog.created_at.desc())
            .limit(limit)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def list_for_skill(
        self,
        skill_id: uuid.UUID,
        *,
        limit: int = 100,
    ) -> list[AgentActivityLog]:
        """List agent activity logs for a skill, most recent first."""
        stmt = self._scoped(
            select(AgentActivityLog)
            .where(AgentActivityLog.skill_id == skill_id)
            .order_by(AgentActivityLog.created_at.desc())
            .limit(limit)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def list_for_session(
        self,
        session_id: str,
    ) -> list[AgentActivityLog]:
        """List all agent activity events in a session."""
        stmt = self._scoped(
            select(AgentActivityLog)
            .where(AgentActivityLog.session_id == session_id)
            .order_by(AgentActivityLog.created_at.asc())
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())
