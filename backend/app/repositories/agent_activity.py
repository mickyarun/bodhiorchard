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

"""Agent activity log repository."""

import uuid
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_activity import AgentActivityLog
from app.models.bud import BUDDocument
from app.models.tracked_repository import TrackedRepository
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

    async def list_recent_with_repo_bud(
        self, event_types: list[str], *, limit: int = 10
    ) -> list[tuple[AgentActivityLog, str | None, int | None, str | None]]:
        """Recent activity rows joined with repo name and BUD info.

        Returns ``(log, repo_name, bud_number, bud_title)`` tuples.
        """
        stmt = self._scoped(
            select(
                AgentActivityLog,
                TrackedRepository.name.label("repo_name"),
                BUDDocument.bud_number.label("bud_number"),
                BUDDocument.title.label("bud_title"),
            )
            .outerjoin(TrackedRepository, AgentActivityLog.repo_id == TrackedRepository.id)
            .outerjoin(BUDDocument, AgentActivityLog.bud_id == BUDDocument.id)
            .where(AgentActivityLog.event_type.in_(event_types))
            .order_by(AgentActivityLog.created_at.desc())
            .limit(limit)
        )
        result = await self._db.execute(stmt)
        return [(row[0], row.repo_name, row.bud_number, row.bud_title) for row in result.all()]

    async def count_skill_completions_by_user_in_window(
        self, since: datetime, until: datetime
    ) -> dict[uuid.UUID, int]:
        """Count ``skill_completed`` events per user in [since, until)."""
        stmt = self._scoped(
            select(AgentActivityLog.user_id, func.count().label("cnt"))
            .where(
                AgentActivityLog.event_type == "skill_completed",
                AgentActivityLog.created_at >= since,
                AgentActivityLog.created_at < until,
                AgentActivityLog.user_id.isnot(None),
            )
            .group_by(AgentActivityLog.user_id)
        )
        result = await self._db.execute(stmt)
        return {row.user_id: row.cnt for row in result.all()}

    async def commit_sha_exists(self, commit_sha: str) -> bool:
        """Return True if a commit event with this SHA is already recorded."""
        stmt = self._scoped(
            select(AgentActivityLog.id)
            .where(
                AgentActivityLog.event_type == "commit",
                AgentActivityLog.commit_sha == commit_sha,
            )
            .limit(1)
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def backfill_session_bud(self, session_id: str, bud_id: uuid.UUID) -> None:
        """Set ``bud_id`` on prior session events that lacked one.

        Hooks may emit events before a BUD has been resolved (e.g. before
        a branch matches a BUD pattern). When a later event in the same
        session does resolve a BUD, we retroactively link the earlier
        events so the activity timeline is complete.
        """
        stmt = (
            update(AgentActivityLog)
            .where(
                AgentActivityLog.session_id == session_id,
                AgentActivityLog.org_id == self._org_id,
                AgentActivityLog.bud_id.is_(None),
            )
            .values(bud_id=bud_id)
        )
        await self._db.execute(stmt)

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
