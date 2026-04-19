# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Single entry point for recording BUD timeline events."""

import uuid

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
    detail: dict | None = None,
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
