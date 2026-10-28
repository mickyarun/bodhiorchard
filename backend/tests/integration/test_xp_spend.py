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

"""Spending skill points (vehicle, house) and the greeting bonus over HTTP."""

from __future__ import annotations

import asyncio
import uuid

import pytest
from httpx import AsyncClient

from app.services.sp_service import award_sp
from tests.integration.gamification_support import join_org, make_org, xp_row
from tests.integration.leave_support import Factory, as_user, give_role

pytestmark = pytest.mark.integration
VEHICLE = "/api/v1/xp/unlock-vehicle"
HOUSE = "/api/v1/xp/upgrade-house"
GREET = "/api/v1/xp/claim-greeting-bonus"


async def _fund(factory: Factory, org: uuid.UUID, user: uuid.UUID, amount: float) -> None:
    async with factory() as db:
        await award_sp(
            db, user_id=user, org_id=org, amount=amount, source="t", source_ref=str(uuid.uuid4())
        )
        await db.commit()


async def _sp(factory: Factory, org: uuid.UUID, user: uuid.UUID) -> float:
    row = await xp_row(factory, org, user)
    return float(row.skill_points) if row else 0.0


async def test_a_vehicle_costs_its_price_once(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """Too poor is refused, the purchase deducts, a second purchase is a conflict."""
    org, (dev,) = await make_org(pg_session_factory, "Dev")
    headers = as_user(dev, org)
    await _fund(pg_session_factory, org, dev, 49.75)
    poor = await client.post(VEHICLE, json={"vehicle_id": "horse"}, headers=headers)
    assert poor.status_code == 400 and "Insufficient" in poor.json()["detail"]
    await _fund(pg_session_factory, org, dev, 10)
    bought = await client.post(VEHICLE, json={"vehicle_id": "horse"}, headers=headers)
    assert bought.status_code == 200, bought.text
    assert bought.json()["vehicle_unlocks"] == ["horse"]
    assert bought.json()["remaining_skill_points"] == pytest.approx(9.75)
    again = await client.post(VEHICLE, json={"vehicle_id": "horse"}, headers=headers)
    assert again.status_code == 409
    assert await _sp(pg_session_factory, org, dev) == pytest.approx(9.75)


async def test_an_unknown_vehicle_is_refused_without_spending(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """Only listed vehicles can be bought."""
    org, (dev,) = await make_org(pg_session_factory, "Dev")
    await _fund(pg_session_factory, org, dev, 100)
    response = await client.post(VEHICLE, json={"vehicle_id": "rocket"}, headers=as_user(dev, org))
    assert response.status_code == 400
    assert await _sp(pg_session_factory, org, dev) == 100


async def test_the_house_goes_up_one_tier_at_a_time(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """Skipping a tier, an unknown tier and a short balance are refused; tier 2 costs 50."""
    org, (dev,) = await make_org(pg_session_factory, "Dev")
    headers = as_user(dev, org)
    await _fund(pg_session_factory, org, dev, 60)
    for tier in (3, 9, 1):
        refused = await client.post(HOUSE, json={"target_tier": tier}, headers=headers)
        assert refused.status_code == 400, tier
    upgraded = await client.post(HOUSE, json={"target_tier": 2}, headers=headers)
    assert upgraded.status_code == 200, upgraded.text
    assert upgraded.json() == {"success": True, "remaining_skill_points": 10, "house_level": 2}
    short = await client.post(HOUSE, json={"target_tier": 3}, headers=headers)
    assert short.status_code == 400 and "Insufficient" in short.json()["detail"]
    row = await xp_row(pg_session_factory, org, dev)
    assert row is not None and row.house_level == 2 and float(row.skill_points) == 10


async def test_spending_in_one_org_uses_that_orgs_balance(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """Skill points earned in another org cannot buy anything here, nor are they spent."""
    org, (dev,) = await make_org(pg_session_factory, "Dev")
    rich_org, _ = await make_org(pg_session_factory)
    await join_org(pg_session_factory, rich_org, dev)
    await _fund(pg_session_factory, rich_org, dev, 500)
    response = await client.post(VEHICLE, json={"vehicle_id": "horse"}, headers=as_user(dev, org))
    assert response.status_code == 400 and "Insufficient" in response.json()["detail"]
    assert await _sp(pg_session_factory, rich_org, dev) == 500


async def test_two_simultaneous_purchases_spend_once(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """A double-click buys the vehicle once: one success, one conflict, one charge."""
    org, (dev,) = await make_org(pg_session_factory, "Dev")
    await _fund(pg_session_factory, org, dev, 60)
    headers = as_user(dev, org)
    responses = await asyncio.gather(
        *(client.post(VEHICLE, json={"vehicle_id": "horse"}, headers=headers) for _ in range(2))
    )
    assert sorted(r.status_code for r in responses) == [200, 409]
    row = await xp_row(pg_session_factory, org, dev)
    assert row is not None and row.vehicle_unlocks == ["horse"]
    assert float(row.skill_points) == 10


async def test_greeting_a_colleague_pays_once_per_pair(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """The first greeting of each colleague earns 0.25 SP; repeats earn nothing."""
    org, (dev, ana, bo) = await make_org(pg_session_factory, "Dev", "Ana", "Bo")
    headers = as_user(dev, org)
    first = await client.post(GREET, json={"target_user_id": str(ana)}, headers=headers)
    assert first.json() == {"awarded": True, "skill_points": 0.25, "sp_earned": 0.25}
    repeat = await client.post(GREET, json={"target_user_id": str(ana)}, headers=headers)
    assert repeat.json() == {"awarded": False, "reason": "already_greeted"}
    other = await client.post(GREET, json={"target_user_id": str(bo)}, headers=headers)
    assert other.json()["skill_points"] == 0.5
    assert await _sp(pg_session_factory, org, dev) == 0.5


async def test_greeting_needs_a_target(client: AsyncClient, pg_session_factory: Factory) -> None:
    """No target means no award."""
    org, (dev,) = await make_org(pg_session_factory, "Dev")
    response = await client.post(GREET, json={}, headers=as_user(dev, org))
    assert response.status_code == 400
    assert await xp_row(pg_session_factory, org, dev) is None


async def test_greeting_needs_engineering_access(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """A member without the engineering workspace (sales) cannot claim the bonus."""
    org, (seller, colleague) = await make_org(pg_session_factory, "Seller", "Colleague")
    await give_role(pg_session_factory, org, seller, "sales")
    response = await client.post(
        GREET, json={"target_user_id": str(colleague)}, headers=as_user(seller, org)
    )
    assert response.status_code == 403
    assert await xp_row(pg_session_factory, org, seller) is None
