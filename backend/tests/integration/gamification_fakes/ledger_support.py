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

"""Readers for the reward ledger: SP events, SP balances and XP event counts."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select

from app.models.developer_xp import DeveloperXP, RewardEvent, RewardType
from tests.fakes.seed import Factory


async def sp_ledger(factory: Factory, org_id: uuid.UUID) -> dict[str, float]:
    """``source_ref -> amount`` for every SP reward event in the org.

    Every SP award is keyed by a ``source_ref``; an event without one would be
    invisible here, so it fails the test instead of being dropped.
    """
    async with factory() as db:
        rows = list(
            await db.scalars(
                select(RewardEvent).where(
                    RewardEvent.org_id == org_id, RewardEvent.type == RewardType.SP
                )
            )
        )
    unkeyed = [r.source for r in rows if not r.source_ref]
    assert not unkeyed, f"SP events without a source_ref: {unkeyed}"
    return {str(r.source_ref): float(r.amount) for r in rows}


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
        count = await db.scalar(
            select(func.count(RewardEvent.id)).where(
                RewardEvent.org_id == org_id, RewardEvent.type == RewardType.XP
            )
        )
        return int(count or 0)


async def org_sp_total(factory: Factory, org_id: uuid.UUID) -> float:
    """Sum of every member's SP balance in the org."""
    async with factory() as db:
        total = await db.scalar(
            select(func.coalesce(func.sum(DeveloperXP.skill_points), 0)).where(
                DeveloperXP.org_id == org_id
            )
        )
        return float(total or 0)


async def assert_nobody_paid(factory: Factory, org_id: uuid.UUID) -> None:
    """No SP event was written and no member of the org holds any SP."""
    assert await sp_ledger(factory, org_id) == {}
    assert await org_sp_total(factory, org_id) == 0.0
