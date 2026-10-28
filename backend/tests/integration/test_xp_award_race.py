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

"""An XP award that loses the dedup race must not move the total.

``award_xp`` checks ``source_ref`` before it locks the user's row, so two
concurrent deliveries of the same event can both pass the check. The unique
index on ``reward_events`` then rejects the second insert; this pins that
the second caller's total is left as it was.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import pytest
from sqlalchemy import func, select

from app.models.developer_xp import DeveloperXP, RewardEvent
from app.repositories.developer_xp import RewardEventRepository
from app.services import xp_service
from app.services.xp_service import award_xp
from tests.integration.leave_support import Factory, setup_org

pytestmark = pytest.mark.integration


async def _award(factory: Factory, org: uuid.UUID, user: uuid.UUID, ref: str) -> bool:
    async with factory() as db:
        result = await award_xp(
            db, user_id=user, org_id=org, amount=20, source="pr", source_ref=ref
        )
        await db.commit()
        return result is not None


async def _state(factory: Factory, org: uuid.UUID, user: uuid.UUID) -> tuple[int, int]:
    async with factory() as db:
        total = await db.scalar(
            select(DeveloperXP.total_xp).where(
                DeveloperXP.org_id == org, DeveloperXP.user_id == user
            )
        )
        count = await db.scalar(
            select(func.count()).where(RewardEvent.org_id == org, RewardEvent.user_id == user)
        )
        return int(total or 0), int(count or 0)


async def test_a_duplicate_that_slips_past_the_check_does_not_pay(
    pg_session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The unique index rejects the replay: the total stays and no toast is sent."""
    sent: list[tuple[str, Any]] = []
    monkeypatch.setattr(
        xp_service, "publish", lambda topic, payload: sent.append((topic, payload))
    )
    org, (dev,), _ = await setup_org(pg_session_factory, "Dev")
    ref = f"pr:{uuid.uuid4()}"
    assert await _award(pg_session_factory, org, dev, ref)
    assert len(sent) == 1

    async def _missed(self: RewardEventRepository, source_ref: str) -> bool:
        return False

    monkeypatch.setattr(RewardEventRepository, "has_source_ref", _missed)
    assert not await _award(pg_session_factory, org, dev, ref)
    assert await _state(pg_session_factory, org, dev) == (20, 1)
    assert [topic for topic, _ in sent] == [f"xp:{dev}"]


async def test_concurrent_deliveries_of_one_event_pay_once(
    pg_session_factory: Factory,
) -> None:
    """Two sessions awarding the same reference at once leave a single award."""
    org, (dev,), _ = await setup_org(pg_session_factory, "Dev")
    ref = f"pr:{uuid.uuid4()}"
    results = await asyncio.gather(*(_award(pg_session_factory, org, dev, ref) for _ in range(2)))
    assert sorted(results) == [False, True]
    assert await _state(pg_session_factory, org, dev) == (20, 1)
