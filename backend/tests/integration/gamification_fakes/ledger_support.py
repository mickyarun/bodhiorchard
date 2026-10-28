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

"""Readers for the reward ledger: SP events, SP balances and the XP event count."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.models.developer_xp import DeveloperXP, RewardEvent, RewardType
from tests.fakes.seed import Factory


async def sp_ledger(factory: Factory, org_id: uuid.UUID) -> dict[str, float]:
    """``source_ref -> amount`` for every SP reward event in the org."""
    async with factory() as db:
        rows = await db.scalars(
            select(RewardEvent).where(
                RewardEvent.org_id == org_id, RewardEvent.type == RewardType.SP
            )
        )
        return {r.source_ref: float(r.amount) for r in rows if r.source_ref}


async def sp_balance(factory: Factory, org_id: uuid.UUID, user_id: uuid.UUID) -> float:
    """The member's SP balance in the org (0 when they have no XP row yet)."""
    async with factory() as db:
        value = await db.scalar(
            select(DeveloperXP.skill_points).where(
                DeveloperXP.org_id == org_id, DeveloperXP.user_id == user_id
            )
        )
        return float(value or 0)


async def xp_event_count(factory: Factory, org_id: uuid.UUID) -> int:
    """How many XP reward events the org has; games must keep this at zero."""
    async with factory() as db:
        rows = await db.scalars(
            select(RewardEvent.id).where(
                RewardEvent.org_id == org_id, RewardEvent.type == RewardType.XP
            )
        )
        return len(list(rows))
