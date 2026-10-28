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

"""Where a streak day starts and ends, and the "is the streak source wired" signal.

A streak day is a UTC calendar day: neither the org nor the member has a
timezone the streak reads. These tests pin that, at 23:59 / 00:01 on both
sides of UTC midnight and for members far from UTC, so a change to local-day
streaks is a deliberate, visible decision.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest
from httpx import AsyncClient

from app.models.dev_activity import DevActivityLog
from app.services import xp_service
from tests.fakes.seed import Factory, auth_headers, seed_member, seed_org
from tests.integration.gamification_fakes.streak_support import (
    FrozenClock,
    install_clock,
    rewards,
    streak_row,
    tick,
)

pytestmark = pytest.mark.integration

KOLKATA = ZoneInfo("Asia/Kolkata")
LOS_ANGELES = ZoneInfo("America/Los_Angeles")


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> type[FrozenClock]:
    """Let each test move ``xp_service``'s clock to a wall time of its choosing."""
    return install_clock(monkeypatch, xp_service, datetime(2026, 3, 2, 12, 0, tzinfo=UTC))


async def _streak_after(
    factory: Factory, clock: type[FrozenClock], *moments: datetime
) -> tuple[int, int]:
    """Record one activity at each wall time; return (streak, XP events)."""
    org = await seed_org(factory)
    dev = await seed_member(factory, org.org_id, "dev")
    streak = 0
    for moment in moments:
        clock.set_local(moment)
        streak = await tick(factory, org.org_id, dev)
    return streak, len(await rewards(factory, org.org_id, dev))


async def test_23_59_and_00_01_utc_are_two_consecutive_streak_days(
    app_sessions: Factory, clock: type[FrozenClock]
) -> None:
    late = datetime(2026, 3, 1, 23, 59, tzinfo=UTC)
    early = datetime(2026, 3, 2, 0, 1, tzinfo=UTC)

    assert await _streak_after(app_sessions, clock, late, early) == (2, 2)


async def test_local_midnight_east_of_utc_is_still_one_streak_day(
    app_sessions: Factory, clock: type[FrozenClock]
) -> None:
    """23:59 and 00:01 in Kolkata are 18:29 and 18:31 UTC on the same UTC day."""
    late = datetime(2026, 3, 1, 23, 59, tzinfo=KOLKATA)
    early = datetime(2026, 3, 2, 0, 1, tzinfo=KOLKATA)

    assert await _streak_after(app_sessions, clock, late, early) == (1, 1)


async def test_one_local_working_day_west_of_utc_can_count_as_two_streak_days(
    app_sessions: Factory, clock: type[FrozenClock]
) -> None:
    """09:00 and 17:30 Pacific on one local day fall either side of UTC midnight."""
    morning = datetime(2026, 3, 2, 9, 0, tzinfo=LOS_ANGELES)
    evening = datetime(2026, 3, 2, 17, 30, tzinfo=LOS_ANGELES)

    assert await _streak_after(app_sessions, clock, morning, evening) == (2, 2)


async def test_a_skipped_utc_day_resets_even_across_a_short_wall_clock_gap(
    app_sessions: Factory, clock: type[FrozenClock]
) -> None:
    """23:59 on the 3rd to 00:01 on the 5th is barely a day of wall time but skips the 4th."""
    org = await seed_org(app_sessions)
    dev = await seed_member(app_sessions, org.org_id, "dev")
    for moment in (
        datetime(2026, 3, 1, 23, 59, tzinfo=UTC),
        datetime(2026, 3, 2, 0, 1, tzinfo=UTC),
    ):
        clock.set_local(moment)
        await tick(app_sessions, org.org_id, dev)
    clock.set_local(datetime(2026, 3, 3, 23, 59, tzinfo=UTC))
    assert await tick(app_sessions, org.org_id, dev) == 3
    clock.set_local(datetime(2026, 3, 5, 0, 1, tzinfo=UTC))
    assert await tick(app_sessions, org.org_id, dev) == 1

    row = await streak_row(app_sessions, org.org_id, dev)
    assert (row.streak_count, row.streak_best, row.last_active_date) == (1, 3, date(2026, 3, 5))


async def _profile(client: AsyncClient, user: uuid.UUID, org: uuid.UUID) -> dict[str, object]:
    response = await client.get("/api/v1/xp/me", headers=auth_headers(user, org))
    assert response.status_code == 200
    body: dict[str, object] = response.json()
    return body


async def test_the_streak_source_signal_turns_on_with_this_orgs_first_hook_event(
    client: AsyncClient, app_sessions: Factory
) -> None:
    org = await seed_org(app_sessions)
    other = await seed_org(app_sessions)
    async with app_sessions() as db:
        db.add(DevActivityLog(org_id=other.org_id, event_type="commit", source="hook"))
        await db.commit()

    before = await _profile(client, org.owner_id, org.org_id)
    async with app_sessions() as db:
        db.add(DevActivityLog(org_id=org.org_id, event_type="commit", source="hook"))
        await db.commit()
    after = await _profile(client, org.owner_id, org.org_id)

    assert (before["streak_source_connected"], before["streak_count"]) == (False, 0)
    assert after["streak_source_connected"] is True
