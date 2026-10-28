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

"""XP profile, leaderboard and history over HTTP: defaults, ranking and tenancy."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.models.user import User
from app.services.xp_service import award_xp
from tests.integration.gamification_support import join_org, make_org
from tests.integration.leave_support import Factory, as_user

pytestmark = pytest.mark.integration


async def _give(factory: Factory, org: uuid.UUID, user: uuid.UUID, amount: float) -> None:
    async with factory() as db:
        await award_xp(
            db, user_id=user, org_id=org, amount=amount, source="t", source_ref=str(uuid.uuid4())
        )
        await db.commit()


async def test_a_new_member_sees_the_starting_profile(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """No XP row yet means level one, no streak and the level-one unlocks."""
    org, (dev,) = await make_org(pg_session_factory, "Dev")
    response = await client.get("/api/v1/xp/me", headers=as_user(dev, org))
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["total_xp"], body["level"], body["level_name"]) == (0, 1, "seedling")
    assert (body["xp_to_next_level"], body["next_level_threshold"]) == (100, 100)
    assert body["skill_points"] == 0 and body["house_level"] == 1
    assert body["vehicle_unlocks"] == [] and body["unlocked_accessories"] == []
    assert set(body["unlocked_characters"]) == {"barbarian", "mage"}


async def test_profile_reflects_awards_at_the_top_level(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """At 5000 XP the user is at the last level and nothing remains to earn."""
    org, (dev,) = await make_org(pg_session_factory, "Dev")
    await _give(pg_session_factory, org, dev, 5000)
    body = (await client.get("/api/v1/xp/me", headers=as_user(dev, org))).json()
    assert (body["total_xp"], body["level"], body["level_name"]) == (5000, 5, "ancient_oak")
    assert (body["xp_to_next_level"], body["next_level_threshold"]) == (0, 0)
    assert "shield" in body["unlocked_accessories"]


async def test_leaderboard_ranks_this_orgs_active_members_only(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """Other orgs' XP, other orgs' people and deactivated users never appear."""
    org, (top, low, gone) = await make_org(pg_session_factory, "Top", "Low", "Gone")
    other_org, (outsider,) = await make_org(pg_session_factory, "Outsider")
    await join_org(pg_session_factory, other_org, low)
    await _give(pg_session_factory, org, top, 50)
    await _give(pg_session_factory, org, low, 10)
    await _give(pg_session_factory, org, gone, 900)
    await _give(pg_session_factory, other_org, low, 5000)
    await _give(pg_session_factory, other_org, outsider, 7000)
    async with pg_session_factory() as db:
        user = await db.get(User, gone)
        assert user is not None
        user.is_active = False
        await db.commit()
    board = (await client.get("/api/v1/xp/leaderboard", headers=as_user(top, org))).json()
    assert [(e["name"], e["total_xp"]) for e in board] == [("Top", 50), ("Low", 10)]


async def test_leaderboard_lists_members_with_no_xp_as_level_one(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """Someone who has earned nothing is still listed, with zero."""
    org, (dev, fresh) = await make_org(pg_session_factory, "Dev", "Fresh")
    await _give(pg_session_factory, org, dev, 1)
    board = (await client.get("/api/v1/xp/leaderboard", headers=as_user(dev, org))).json()
    assert board[-1] == {
        "user_id": str(fresh),
        "name": "Fresh",
        "avatar_url": None,
        "total_xp": 0,
        "level": 1,
        "level_name": "seedling",
        "streak_count": 0,
    }


async def test_history_is_your_own_events_in_this_org(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """A colleague's awards and your awards in another org are not listed."""
    org, (dev, peer) = await make_org(pg_session_factory, "Dev", "Peer")
    other_org, _ = await make_org(pg_session_factory)
    await join_org(pg_session_factory, other_org, dev)
    await _give(pg_session_factory, org, dev, 7)
    await _give(pg_session_factory, org, peer, 11)
    await _give(pg_session_factory, other_org, dev, 13)
    history = (await client.get("/api/v1/xp/history", headers=as_user(dev, org))).json()
    assert [(h["type"], h["amount"]) for h in history] == [("xp", 7.0)]


async def test_xp_routes_need_the_engineering_workspace(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """A member without engineering access (sales), or with no token, is refused."""
    org, (plain,) = await make_org(pg_session_factory, "Plain", role="sales")
    for path in ("/api/v1/xp/me", "/api/v1/xp/leaderboard", "/api/v1/xp/history"):
        assert (await client.get(path, headers=as_user(plain, org))).status_code == 403
        assert (await client.get(path)).status_code == 401
