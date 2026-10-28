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

"""Activity streak multipliers and milestone Skill Points around their boundaries.

The streak row is seeded just before each boundary (day 13, 29, ...) and one
more day of activity is recorded with the clock frozen, so every boundary is
exercised without replaying a month of days.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from app.services import xp_service
from tests.fakes.seed import Factory, seed_member, seed_org
from tests.integration.gamification_fakes.frozen_clock import FrozenClock, install_clock
from tests.integration.gamification_fakes.streak_support import (
    rewards,
    seed_streak,
    streak_row,
    tick,
)

pytestmark = pytest.mark.integration

TODAY = date(2026, 3, 2)


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> type[FrozenClock]:
    """Freeze ``xp_service``'s clock at noon UTC on ``TODAY``."""
    return install_clock(monkeypatch, xp_service, datetime(2026, 3, 2, 12, 0, tzinfo=UTC))


@pytest.mark.parametrize(
    ("prior", "xp", "multiplier", "sp"),
    [
        (12, 15.0, 1.5, None),
        (13, 20.0, 2.0, ("sp_streak_14", 0.5)),
        (28, 20.0, 2.0, None),
        (29, 25.0, 2.5, ("sp_streak_30", 1.0)),
        (30, 25.0, 2.5, None),
    ],
    ids=["day-13", "day-14", "day-29", "day-30", "day-31"],
)
async def test_each_boundary_pays_its_multiplier_and_only_14_and_30_pay_sp(
    app_sessions: Factory,
    clock: type[FrozenClock],
    prior: int,
    xp: float,
    multiplier: float,
    sp: tuple[str, float] | None,
) -> None:
    org = await seed_org(app_sessions)
    dev = await seed_member(app_sessions, org.org_id, "dev")
    yesterday = TODAY - timedelta(days=1)
    await seed_streak(
        app_sessions, org.org_id, dev, streak=prior, best=prior, last_active=yesterday
    )

    assert await tick(app_sessions, org.org_id, dev) == prior + 1

    expected = [("xp", f"streak:{dev}:{TODAY.isoformat()}", xp, multiplier)]
    if sp is not None:
        expected.append(("sp", f"{sp[0]}:{dev}:{TODAY.isoformat()}", sp[1], 1.0))
    assert sorted(await rewards(app_sessions, org.org_id, dev)) == sorted(expected)
    row = await streak_row(app_sessions, org.org_id, dev)
    assert (row.streak_best, row.total_xp) == (prior + 1, int(xp))
    assert float(row.skill_points) == (sp[1] if sp else 0.0)


async def test_activity_again_on_milestone_day_pays_the_sp_once(
    app_sessions: Factory, clock: type[FrozenClock]
) -> None:
    org = await seed_org(app_sessions)
    dev = await seed_member(app_sessions, org.org_id, "dev")
    yesterday = TODAY - timedelta(days=1)
    await seed_streak(app_sessions, org.org_id, dev, streak=29, best=29, last_active=yesterday)

    for hour in (9, 13, 23):
        clock.set_local(datetime(2026, 3, 2, hour, 0, tzinfo=UTC))
        assert await tick(app_sessions, org.org_id, dev) == 30

    events = await rewards(app_sessions, org.org_id, dev)
    assert sorted((kind, amount) for kind, _, amount, _ in events) == [("sp", 1.0), ("xp", 25.0)]


async def test_a_broken_30_day_streak_restarts_at_one_and_keeps_the_best(
    app_sessions: Factory, clock: type[FrozenClock]
) -> None:
    org = await seed_org(app_sessions)
    dev = await seed_member(app_sessions, org.org_id, "dev")
    two_days_ago = TODAY - timedelta(days=2)
    await seed_streak(app_sessions, org.org_id, dev, streak=30, best=30, last_active=two_days_ago)

    assert await tick(app_sessions, org.org_id, dev) == 1

    row = await streak_row(app_sessions, org.org_id, dev)
    assert (row.streak_count, row.streak_best, row.total_xp) == (1, 30, 10)
    assert [kind for kind, *_ in await rewards(app_sessions, org.org_id, dev)] == ["xp"]


async def test_a_second_run_to_14_days_earns_the_milestone_again(
    app_sessions: Factory, clock: type[FrozenClock]
) -> None:
    org = await seed_org(app_sessions)
    dev = await seed_member(app_sessions, org.org_id, "dev")
    yesterday = TODAY - timedelta(days=1)
    await seed_streak(app_sessions, org.org_id, dev, streak=13, best=30, last_active=yesterday)

    await tick(app_sessions, org.org_id, dev)

    row = await streak_row(app_sessions, org.org_id, dev)
    assert (row.streak_count, row.streak_best, float(row.skill_points)) == (14, 30, 0.5)
