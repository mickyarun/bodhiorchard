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

"""Daily activity streak: one award per UTC day, continuation, reset and milestones."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest

from app.models.developer_xp import RewardType
from app.services import xp_service
from app.services.xp_service import check_and_award_streak
from tests.integration.gamification_support import events, make_org, xp_row
from tests.integration.leave_support import Factory

pytestmark = pytest.mark.integration

START = date(2026, 3, 1)


class _Clock:
    """Stands in for ``datetime`` inside ``xp_service`` with a settable day."""

    today = START

    @classmethod
    def now(cls, tz: Any = None) -> datetime:
        return datetime(cls.today.year, cls.today.month, cls.today.day, 12, tzinfo=UTC)


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> type[_Clock]:
    """Freeze the streak's notion of today, starting on ``START``."""
    _Clock.today = START
    monkeypatch.setattr(xp_service, "datetime", _Clock)
    return _Clock


async def _tick(factory: Factory, org: uuid.UUID, user: uuid.UUID) -> int:
    async with factory() as db:
        streak = await check_and_award_streak(db, user_id=user, org_id=org)
        await db.commit()
        return streak


async def test_activity_twice_in_a_day_counts_once(
    pg_session_factory: Factory, clock: type[_Clock]
) -> None:
    """The second event of the day neither advances the streak nor pays again."""
    org, (dev,) = await make_org(pg_session_factory, "Dev")
    assert await _tick(pg_session_factory, org, dev) == 1
    assert await _tick(pg_session_factory, org, dev) == 1
    row = await xp_row(pg_session_factory, org, dev)
    assert row is not None and row.total_xp == 10
    assert len(await events(pg_session_factory, org, dev, RewardType.XP)) == 1


async def test_next_day_continues_and_a_gap_resets(
    pg_session_factory: Factory, clock: type[_Clock]
) -> None:
    """Consecutive days build the streak; a skipped day starts over but keeps the best."""
    org, (dev,) = await make_org(pg_session_factory, "Dev")
    assert await _tick(pg_session_factory, org, dev) == 1
    clock.today = START + timedelta(days=1)
    assert await _tick(pg_session_factory, org, dev) == 2
    clock.today = START + timedelta(days=3)
    assert await _tick(pg_session_factory, org, dev) == 1
    row = await xp_row(pg_session_factory, org, dev)
    assert row is not None and (row.streak_count, row.streak_best) == (1, 2)
    assert row.total_xp == 30


async def test_a_week_long_streak_pays_the_multiplier(
    pg_session_factory: Factory, clock: type[_Clock]
) -> None:
    """Day seven pays 15 XP (1.5x) instead of 10."""
    org, (dev,) = await make_org(pg_session_factory, "Dev")
    for offset in range(7):
        clock.today = START + timedelta(days=offset)
        await _tick(pg_session_factory, org, dev)
    amounts = sorted(float(e.amount) for e in await events(pg_session_factory, org, dev))
    assert amounts == [10] * 6 + [15]


async def test_day_fourteen_also_awards_the_streak_skill_points(
    pg_session_factory: Factory, clock: type[_Clock]
) -> None:
    """The 14-day milestone pays 0.5 SP once, alongside the day's XP."""
    org, (dev,) = await make_org(pg_session_factory, "Dev")
    for offset in range(14):
        clock.today = START + timedelta(days=offset)
        await _tick(pg_session_factory, org, dev)
    await _tick(pg_session_factory, org, dev)
    sp = await events(pg_session_factory, org, dev, RewardType.SP)
    assert [(e.source, float(e.amount)) for e in sp] == [("sp_streak", 0.5)]
    row = await xp_row(pg_session_factory, org, dev)
    assert row is not None and float(row.skill_points) == 0.5 and row.streak_count == 14
