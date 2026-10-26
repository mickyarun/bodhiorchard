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

"""Append-only access to the celebration settings audit trail."""

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.celebration_config_event import CelebrationConfigAction, CelebrationConfigEvent
from app.repositories.base import BaseRepository


class CelebrationConfigEventRepository(BaseRepository[CelebrationConfigEvent]):
    """Records who changed an org's celebration settings. Never updates or deletes."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        """Initialize the repository.

        Args:
            db: Async SQLAlchemy session.
            org_id: Tenant whose trail this repository writes.
        """
        super().__init__(CelebrationConfigEvent, db, org_id=org_id)
        self._org = org_id

    async def append(
        self,
        *,
        actor_id: uuid.UUID,
        action: CelebrationConfigAction,
        changes: dict[str, Any],
    ) -> CelebrationConfigEvent:
        """Record one change. ``changes`` maps field → ``[old, new]``."""
        event = CelebrationConfigEvent(
            org_id=self._org, actor_id=actor_id, action=action, changes=changes
        )
        self._db.add(event)
        await self._db.flush()
        return event
