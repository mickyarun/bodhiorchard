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

"""Data access repository for feature Q&A sessions."""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feature_qa_session import FeatureQASession, FeatureQAStatus
from app.repositories.base import BaseRepository


class FeatureQASessionRepository(BaseRepository[FeatureQASession]):
    """Repository for FeatureQASession queries, scoped to an organization."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        """Initialize the repository.

        Args:
            db: Async SQLAlchemy session.
            org_id: Organization UUID for tenant scoping.
        """
        super().__init__(FeatureQASession, db, org_id=org_id)

    async def get_by_thread(self, channel: str, thread_ts: str) -> FeatureQASession | None:
        """Find a Q&A session by its Slack thread.

        Args:
            channel: Slack channel ID.
            thread_ts: Thread parent timestamp.

        Returns:
            The matching FeatureQASession or None.
        """
        stmt = self._scoped(
            select(FeatureQASession).where(
                FeatureQASession.channel == channel,
                FeatureQASession.thread_ts == thread_ts,
            )
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def update_status(self, session: FeatureQASession, status: FeatureQAStatus) -> None:
        """Update session status and flush.

        Args:
            session: The session to update.
            status: New status value.
        """
        session.status = status
        await self._db.flush()

    async def update_context(self, session: FeatureQASession, context: dict[str, Any]) -> None:
        """Update session context JSONB and flush.

        Args:
            session: The session to update.
            context: New context dict (replaces existing).
        """
        session.context = context
        await self._db.flush()
