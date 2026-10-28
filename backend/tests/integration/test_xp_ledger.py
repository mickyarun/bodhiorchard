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

"""XP awards against a real database: totals, the audit trail, dedup and tenancy."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from app.services import xp_service
from app.services.xp_service import XPAwardResult, award_xp
from tests.integration.gamification_support import (
    capture_publish,
    events,
    join_org,
    make_org,
    xp_row,
)
from tests.integration.leave_support import Factory

pytestmark = pytest.mark.integration


async def _award(
    factory: Factory, org: uuid.UUID, user: uuid.UUID, amount: float, ref: str | None
) -> XPAwardResult | None:
    async with factory() as db:
        result = await award_xp(
            db, user_id=user, org_id=org, amount=amount, source="test", source_ref=ref
        )
        await db.commit()
        return result


async def test_award_adds_to_the_total_logs_one_event_and_levels_up(
    pg_session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Crossing 100 XP moves seedling to sprout and says so on the user's topic."""
    sent = capture_publish(monkeypatch, xp_service)
    org, (dev,) = await make_org(pg_session_factory, "Dev")
    first = await _award(pg_session_factory, org, dev, 60, f"a:{uuid.uuid4()}")
    second = await _award(pg_session_factory, org, dev, 40, f"b:{uuid.uuid4()}")
    assert first is not None and not first.level_changed and first.new_total == 60
    assert second is not None and second.level_changed
    assert (second.old_level, second.new_level, second.new_level_name) == (1, 2, "sprout")
    row = await xp_row(pg_session_factory, org, dev)
    assert row is not None and (row.total_xp, row.level, row.level_name) == (100, 2, "sprout")
    assert sorted(float(e.amount) for e in await events(pg_session_factory, org, dev)) == [40, 60]
    assert [t for t, _ in sent] == [f"xp:{dev}", f"xp:{dev}"]
    assert [p["event_type"] for _, p in sent] == ["xp_awarded", "level_up"]


async def test_the_same_source_ref_awards_once(pg_session_factory: Factory) -> None:
    """A replayed webhook or job must not pay twice."""
    org, (dev,) = await make_org(pg_session_factory, "Dev")
    ref = f"pr:{uuid.uuid4()}"
    assert await _award(pg_session_factory, org, dev, 25, ref) is not None
    assert await _award(pg_session_factory, org, dev, 25, ref) is None
    row = await xp_row(pg_session_factory, org, dev)
    assert row is not None and row.total_xp == 25
    assert len(await events(pg_session_factory, org, dev)) == 1


@pytest.mark.parametrize("amount", [0, -5, 0.004])
async def test_zero_or_negative_amounts_write_nothing(
    pg_session_factory: Factory, amount: float
) -> None:
    """XP never goes down and an award that rounds to nothing leaves no trace."""
    org, (dev,) = await make_org(pg_session_factory, "Dev")
    assert await _award(pg_session_factory, org, dev, amount, f"z:{uuid.uuid4()}") is None
    assert await xp_row(pg_session_factory, org, dev) is None
    assert await events(pg_session_factory, org, dev) == []


async def test_a_split_keeps_the_fraction_on_the_event_and_rounds_the_total(
    pg_session_factory: Factory,
) -> None:
    """A 25 XP pool split three ways stores 8.33 per event; the total is whole."""
    org, (dev,) = await make_org(pg_session_factory, "Dev")
    result = await _award(pg_session_factory, org, dev, 25 / 3, f"s:{uuid.uuid4()}")
    assert result is not None and result.amount_awarded == 8
    (event,) = await events(pg_session_factory, org, dev)
    assert Decimal(str(event.amount)) == Decimal("8.33")
    row = await xp_row(pg_session_factory, org, dev)
    assert row is not None and row.total_xp == 8


async def test_a_multiplier_scales_the_award(pg_session_factory: Factory) -> None:
    """The multiplier is applied before rounding and recorded on the event."""
    org, (dev,) = await make_org(pg_session_factory, "Dev")
    async with pg_session_factory() as db:
        result = await award_xp(
            db, user_id=dev, org_id=org, amount=10, source="t", source_ref=None, multiplier=1.5
        )
        await db.commit()
    assert result is not None and result.amount_awarded == 15
    (event,) = await events(pg_session_factory, org, dev)
    assert float(event.multiplier) == 1.5 and float(event.amount) == 15


async def test_points_are_kept_per_org_for_a_member_of_two(pg_session_factory: Factory) -> None:
    """The same reference in another org is a separate award on a separate total."""
    org_a, (dev,) = await make_org(pg_session_factory, "Dev")
    org_b, _ = await make_org(pg_session_factory)
    await join_org(pg_session_factory, org_b, dev)
    ref = f"shared:{uuid.uuid4()}"
    assert await _award(pg_session_factory, org_a, dev, 30, ref) is not None
    assert await _award(pg_session_factory, org_b, dev, 5, ref) is not None
    row_a = await xp_row(pg_session_factory, org_a, dev)
    row_b = await xp_row(pg_session_factory, org_b, dev)
    assert row_a is not None and row_a.total_xp == 30
    assert row_b is not None and row_b.total_xp == 5
    assert [float(e.amount) for e in await events(pg_session_factory, org_b, dev)] == [5]
