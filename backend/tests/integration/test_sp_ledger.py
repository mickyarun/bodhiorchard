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

"""Skill point awards and penalties against a real database."""

from __future__ import annotations

import uuid

import pytest

from app.models.developer_xp import RewardType
from app.repositories.developer_xp import RewardEventRepository
from app.services import sp_service
from app.services.sp_service import award_sp, penalize_sp
from tests.integration.gamification_support import capture_publish, events, make_org, xp_row
from tests.integration.leave_support import Factory

pytestmark = pytest.mark.integration


async def _sp(
    factory: Factory, org: uuid.UUID, user: uuid.UUID, amount: float, ref: str | None
) -> float | None:
    async with factory() as db:
        balance = await award_sp(
            db, user_id=user, org_id=org, amount=amount, source="test", source_ref=ref
        )
        await db.commit()
        return balance


async def _balance(factory: Factory, org: uuid.UUID, user: uuid.UUID) -> float:
    row = await xp_row(factory, org, user)
    assert row is not None
    return float(row.skill_points)


async def test_award_returns_the_balance_logs_it_and_never_touches_xp(
    pg_session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SP and XP share a row but are separate currencies."""
    sent = capture_publish(monkeypatch, sp_service)
    org, (dev,) = await make_org(pg_session_factory, "Dev")
    assert await _sp(pg_session_factory, org, dev, 0.25, f"r:{uuid.uuid4()}") == 0.25
    assert await _sp(pg_session_factory, org, dev, 0.5, f"r:{uuid.uuid4()}") == 0.75
    row = await xp_row(pg_session_factory, org, dev)
    assert row is not None and float(row.skill_points) == 0.75 and row.total_xp == 0
    assert len(await events(pg_session_factory, org, dev, RewardType.SP)) == 2
    assert await events(pg_session_factory, org, dev, RewardType.XP) == []
    assert [p["skill_points"] for _, p in sent] == [0.25, 0.75]


async def test_the_same_source_ref_pays_once(pg_session_factory: Factory) -> None:
    """A second award with the same reference is a no-op that returns None."""
    org, (dev,) = await make_org(pg_session_factory, "Dev")
    ref = f"bud:{uuid.uuid4()}"
    assert await _sp(pg_session_factory, org, dev, 1.0, ref) == 1.0
    assert await _sp(pg_session_factory, org, dev, 1.0, ref) is None
    assert await _balance(pg_session_factory, org, dev) == 1.0


async def test_zero_is_a_no_op(pg_session_factory: Factory) -> None:
    """A zero award creates neither a row nor an event."""
    org, (dev,) = await make_org(pg_session_factory, "Dev")
    assert await _sp(pg_session_factory, org, dev, 0, f"z:{uuid.uuid4()}") is None
    assert await xp_row(pg_session_factory, org, dev) is None
    assert await events(pg_session_factory, org, dev) == []


async def test_a_penalty_floors_the_balance_at_zero(pg_session_factory: Factory) -> None:
    """Penalties are negated whatever their sign and never push SP below zero."""
    org, (dev,) = await make_org(pg_session_factory, "Dev")
    await _sp(pg_session_factory, org, dev, 0.25, f"r:{uuid.uuid4()}")
    async with pg_session_factory() as db:
        after = await penalize_sp(
            db, user_id=dev, org_id=org, amount=-1.0, source="bug", source_ref=f"p:{uuid.uuid4()}"
        )
        await db.commit()
    assert after == 0.0
    assert await _balance(pg_session_factory, org, dev) == 0.0
    penalties = [e for e in await events(pg_session_factory, org, dev) if e.source == "bug"]
    assert [float(e.amount) for e in penalties] == [-1.0]


async def test_a_penalty_with_no_balance_stays_at_zero(pg_session_factory: Factory) -> None:
    """A first-ever event that is a penalty creates a zero balance, not a negative one."""
    org, (dev,) = await make_org(pg_session_factory, "Dev")
    assert await _sp(pg_session_factory, org, dev, -0.25, f"p:{uuid.uuid4()}") == 0.0
    assert await _balance(pg_session_factory, org, dev) == 0.0


async def test_losing_the_dedup_race_restores_the_balance(
    pg_session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the pre-check misses a concurrent award the unique index wins, balance intact."""
    org, (dev,) = await make_org(pg_session_factory, "Dev")
    ref = f"race:{uuid.uuid4()}"
    assert await _sp(pg_session_factory, org, dev, 0.5, ref) == 0.5

    async def _missed(self: RewardEventRepository, source_ref: str) -> bool:
        return False

    monkeypatch.setattr(RewardEventRepository, "has_source_ref", _missed)
    assert await _sp(pg_session_factory, org, dev, 0.5, ref) is None
    assert await _balance(pg_session_factory, org, dev) == 0.5
    assert len(await events(pg_session_factory, org, dev, RewardType.SP)) == 1


async def test_sp_in_one_org_is_invisible_in_another(pg_session_factory: Factory) -> None:
    """Balances are per org: awarding in one leaves the other org's row absent."""
    org_a, (dev,) = await make_org(pg_session_factory, "Dev")
    org_b, _ = await make_org(pg_session_factory)
    await _sp(pg_session_factory, org_a, dev, 1.0, f"r:{uuid.uuid4()}")
    assert await xp_row(pg_session_factory, org_b, dev) is None
    assert await events(pg_session_factory, org_b, dev) == []
