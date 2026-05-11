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

"""Data access repository for triage sessions."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.triage_session import TriageSession, TriageStatus
from app.repositories.base import BaseRepository


class TriageSessionRepository(BaseRepository[TriageSession]):
    """Repository for TriageSession queries, scoped to an organization."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        """Initialize the repository.

        Args:
            db: Async SQLAlchemy session.
            org_id: Organization UUID for tenant scoping.
        """
        super().__init__(TriageSession, db, org_id=org_id)

    async def get_by_thread(self, channel: str, thread_ts: str) -> TriageSession | None:
        """Find a triage session by its Slack thread.

        Args:
            channel: Slack channel ID.
            thread_ts: Thread parent timestamp.

        Returns:
            The matching TriageSession or None.
        """
        stmt = self._scoped(
            select(TriageSession).where(
                TriageSession.slack_channel == channel,
                TriageSession.thread_ts == thread_ts,
            )
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_original_msg(
        self, channel: str, original_msg_ts: str
    ) -> TriageSession | None:
        """Find a triage session by the original message that was reacted to.

        Args:
            channel: Slack channel ID.
            original_msg_ts: Timestamp of the message that received the brain emoji.

        Returns:
            The matching TriageSession or None.
        """
        stmt = self._scoped(
            select(TriageSession).where(
                TriageSession.slack_channel == channel,
                TriageSession.original_msg_ts == original_msg_ts,
            )
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_summary_msg(self, channel: str, summary_msg_ts: str) -> TriageSession | None:
        """Find a triage session by the summary message (used for PM approval lookup).

        Args:
            channel: Slack channel ID.
            summary_msg_ts: Timestamp of the bot's triage summary message.

        Returns:
            The matching TriageSession or None.
        """
        stmt = self._scoped(
            select(TriageSession).where(
                TriageSession.slack_channel == channel,
                TriageSession.summary_msg_ts == summary_msg_ts,
            )
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_active_for_org(self) -> list[TriageSession]:
        """List all active triage sessions (not yet completed).

        Returns:
            List of TriageSessions in interviewing, checking, or awaiting_pm status.
        """
        active_statuses = [
            TriageStatus.INTERVIEWING,
            TriageStatus.CHECKING,
            TriageStatus.AWAITING_PM,
        ]
        stmt = self._scoped(
            select(TriageSession)
            .where(TriageSession.status.in_(active_statuses))
            .order_by(TriageSession.created_at.desc())
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def list_by_status(self, status_filter: str | None = None) -> list[TriageSession]:
        """List triage sessions, optionally filtered by status.

        Args:
            status_filter: Optional status string to filter by.

        Returns:
            List of TriageSessions ordered by most recent first.
        """
        stmt = self._scoped(select(TriageSession))
        if status_filter:
            stmt = stmt.where(TriageSession.status == status_filter)
        stmt = stmt.order_by(TriageSession.created_at.desc())
        result = await self._db.execute(stmt)
        return list(result.scalars().all())
