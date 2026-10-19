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

"""Append-only access to the leave configuration trail."""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.leave_config_event import LeaveConfigAction, LeaveConfigEvent

HISTORY_LIMIT = 100


class LeaveConfigEventRepository:
    """Config events, always scoped to one org.

    Deliberately not a ``BaseRepository``: there is no update or delete.
    """

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        """Initialize the repository."""
        self._db = db
        self._org = org_id

    def record(
        self,
        *,
        actor_id: uuid.UUID,
        action: LeaveConfigAction,
        policy_id: uuid.UUID | None,
        changes: dict[str, Any],
    ) -> None:
        """Stage one event in the caller's transaction."""
        self._db.add(
            LeaveConfigEvent(
                org_id=self._org,
                actor_id=actor_id,
                policy_id=policy_id,
                action=action,
                changes=changes,
            )
        )

    async def for_policy(self, policy_id: uuid.UUID) -> list[LeaveConfigEvent]:
        """A policy's most recent changes, newest first."""
        stmt = (
            select(LeaveConfigEvent)
            .where(LeaveConfigEvent.org_id == self._org, LeaveConfigEvent.policy_id == policy_id)
            .order_by(LeaveConfigEvent.created_at.desc())
        )
        result = await self._db.execute(stmt.limit(HISTORY_LIMIT))
        return list(result.scalars().all())
