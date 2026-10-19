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

"""Slack approval prompts sent for leave requests."""

import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.leave_slack_prompt import LeaveSlackPrompt
from app.repositories.base import BaseRepository


class LeaveSlackPromptRepository(BaseRepository[LeaveSlackPrompt]):
    """Prompts, always scoped to one org."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        """Initialize the repository."""
        super().__init__(LeaveSlackPrompt, db, org_id=org_id)
        self._org = org_id

    async def remember(
        self, request_id: uuid.UUID, user_id: uuid.UUID, channel: str, ts: str
    ) -> None:
        """Record a sent prompt (one per approver per request)."""
        await self._db.execute(
            insert(LeaveSlackPrompt)
            .values(
                id=uuid.uuid4(),
                org_id=self._org,
                request_id=request_id,
                user_id=user_id,
                channel=channel,
                ts=ts,
            )
            .on_conflict_do_nothing(constraint="uq_leave_slack_prompts_request_user")
        )

    async def for_request(self, request_id: uuid.UUID) -> list[LeaveSlackPrompt]:
        """Every prompt sent for a request."""
        result = await self._db.execute(
            self._scoped(select(LeaveSlackPrompt).where(LeaveSlackPrompt.request_id == request_id))
        )
        return list(result.scalars().all())
