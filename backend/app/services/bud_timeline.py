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

"""Single entry point for recording BUD timeline events."""

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bud import BUDTimelineEvent
from app.repositories.bud_timeline import BUDTimelineRepository


async def record_event(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud_id: uuid.UUID,
    event_type: str,
    actor_id: uuid.UUID | None = None,
    actor_name: str | None = None,
    detail: dict[str, Any] | None = None,
) -> BUDTimelineEvent:
    """Append a timeline event to a BUD."""
    repo = BUDTimelineRepository(db, org_id=org_id)
    event = BUDTimelineEvent(
        org_id=org_id,
        bud_id=bud_id,
        event_type=event_type,
        actor_id=actor_id,
        actor_name=actor_name,
        detail=detail,
    )
    await repo.add(event)
    await repo.flush()
    return event
