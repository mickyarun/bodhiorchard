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

"""Read-side helpers for the BUD lifecycle integration tests.

Each helper opens its own session so assertions see committed state,
never a stale identity map from the session that did the write.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select

from app.models.bud import BUDDocument, BUDTimelineEvent
from app.models.developer_xp import DeveloperXP, RewardEvent, RewardType
from tests.integration.bud_lifecycle_support import Factory


async def load_bud(factory: Factory, bud_id: uuid.UUID) -> BUDDocument:
    """Fresh read of a BUD row (new session, so no stale identity map)."""
    async with factory() as db:
        bud = await db.get(BUDDocument, bud_id)
        assert bud is not None
        return bud


async def timeline(factory: Factory, bud_id: uuid.UUID, event_type: str) -> list[dict[str, Any]]:
    """``detail`` of every timeline event of ``event_type`` on the BUD."""
    async with factory() as db:
        rows = await db.scalars(
            select(BUDTimelineEvent).where(
                BUDTimelineEvent.bud_id == bud_id,
                BUDTimelineEvent.event_type == event_type,
            )
        )
        return [row.detail or {} for row in rows]


async def xp_events(factory: Factory, org_id: uuid.UUID) -> dict[str, float]:
    """Map ``source_ref -> amount`` for every XP reward event in the org."""
    async with factory() as db:
        rows = await db.scalars(
            select(RewardEvent).where(
                RewardEvent.org_id == org_id, RewardEvent.type == RewardType.XP
            )
        )
        return {r.source_ref: float(r.amount) for r in rows if r.source_ref}


async def count_rows(factory: Factory, model: Any, org_id: uuid.UUID) -> int:
    """Number of ``model`` rows that belong to ``org_id``."""
    async with factory() as db:
        result = await db.execute(
            select(func.count()).select_from(model).where(model.org_id == org_id)
        )
        return int(result.scalar_one())


async def xp_ledger(factory: Factory, org_id: uuid.UUID, user_id: uuid.UUID) -> tuple[int, int]:
    """``(DeveloperXP.total_xp, rounded sum of the user's XP events)``.

    The two must always agree: the aggregate is only ever moved by an
    award that also writes its audit event.
    """
    async with factory() as db:
        total = await db.scalar(
            select(DeveloperXP.total_xp).where(
                DeveloperXP.org_id == org_id, DeveloperXP.user_id == user_id
            )
        )
        events = await db.scalars(
            select(RewardEvent.amount).where(
                RewardEvent.org_id == org_id,
                RewardEvent.user_id == user_id,
                RewardEvent.type == RewardType.XP,
            )
        )
        return int(total or 0), sum(round(float(a)) for a in events)
