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

"""Game results over the bridge: recorded, idempotent, tenant-checked, and never XP.

XP is for real development work only. Every game write path (mini-games,
Backlash, races) is posted here against a real database and the players'
XP and skill points are checked to be exactly what they were before.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.services.xp_service import award_xp
from tests.integration.gamification_support import (
    bridge,
    events,
    make_org,
    org_reward_count,
    xp_row,
)
from tests.integration.leave_support import Factory, as_user

pytestmark = pytest.mark.integration
BRIDGE = "/api/v1/internal/colyseus"


def _play(org: uuid.UUID, user: uuid.UUID, score: int, session: str) -> dict[str, object]:
    return {
        "sessionId": session,
        "orgId": str(org),
        "userId": str(user),
        "userName": "Player",
        "game": "firefly",
        "score": score,
    }


async def _seed_xp(factory: Factory, org: uuid.UUID, user: uuid.UUID) -> None:
    async with factory() as db:
        await award_xp(db, user_id=user, org_id=org, amount=40, source="pr", source_ref="seed")
        await db.commit()


async def _xp_untouched(factory: Factory, org: uuid.UUID, user: uuid.UUID) -> None:
    row = await xp_row(factory, org, user)
    assert row is not None and row.total_xp == 40 and float(row.skill_points) == 0
    assert [e.source for e in await events(factory, org, user)] == ["pr"]


async def test_a_minigame_play_records_a_score_and_no_xp(
    client: AsyncClient, pg_session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The play shows up in the game's status; the XP ledger is unchanged."""
    headers = bridge(monkeypatch)
    org, (player,) = await make_org(pg_session_factory, "Player")
    await _seed_xp(pg_session_factory, org, player)
    posted = await client.post(
        f"{BRIDGE}/minigame-results",
        json=_play(org, player, 12, f"s-{uuid.uuid4()}"),
        headers=headers,
    )
    assert posted.status_code == 200, posted.text
    assert posted.json()["recorded"] is True and posted.json()["best_score"] == 12
    await _xp_untouched(pg_session_factory, org, player)
    status = (await client.get("/api/v1/minigames/status", headers=as_user(player, org))).json()
    firefly = next(g for g in status["games"] if g["key"] == "firefly")
    assert firefly["best_score"] == 12 and firefly["played_today"] is True
    assert status["streak_count"] == 1


async def test_a_replayed_session_is_not_counted_twice(
    client: AsyncClient, pg_session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A bridge retry returns the stored result and leaves plays at one."""
    headers = bridge(monkeypatch)
    org, (player,) = await make_org(pg_session_factory, "Player")
    body = _play(org, player, 9, f"s-{uuid.uuid4()}")
    await client.post(f"{BRIDGE}/minigame-results", json=body, headers=headers)
    replay = await client.post(f"{BRIDGE}/minigame-results", json=body, headers=headers)
    assert replay.json()["recorded"] is False and replay.json()["best_score"] == 9
    board = await client.get(
        "/api/v1/minigames/leaderboard", params={"game": "firefly"}, headers=as_user(player, org)
    )
    assert [(e["best_score"], e["plays"]) for e in board.json()["entries"]] == [(9, 1)]
    assert await org_reward_count(pg_session_factory, org) == (0, 0)


async def test_a_rejected_score_does_not_burn_the_session(
    client: AsyncClient, pg_session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Over the game's cap is refused and the same session can still be recorded."""
    headers = bridge(monkeypatch)
    org, (player,) = await make_org(pg_session_factory, "Player")
    session = f"s-{uuid.uuid4()}"
    over = await client.post(
        f"{BRIDGE}/minigame-results", json=_play(org, player, 51, session), headers=headers
    )
    assert over.status_code == 422
    ok = await client.post(
        f"{BRIDGE}/minigame-results", json=_play(org, player, 50, session), headers=headers
    )
    assert ok.status_code == 200 and ok.json()["recorded"] is True


async def test_bridge_writes_need_the_secret_and_an_org_member(
    client: AsyncClient, pg_session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A wrong secret is 401; a player from another org is 404 and nothing is stored."""
    headers = bridge(monkeypatch)
    org, (player,) = await make_org(pg_session_factory, "Player")
    _other, (outsider,) = await make_org(pg_session_factory, "Outsider")
    body = _play(org, player, 5, f"s-{uuid.uuid4()}")
    wrong = await client.post(
        f"{BRIDGE}/minigame-results", json=body, headers={"X-Bridge-Secret": "nope"}
    )
    assert wrong.status_code == 401
    assert (await client.post(f"{BRIDGE}/minigame-results", json=body)).status_code == 401
    foreign = _play(org, outsider, 5, f"s-{uuid.uuid4()}")
    refused = await client.post(f"{BRIDGE}/minigame-results", json=foreign, headers=headers)
    assert refused.status_code == 404
    board = await client.get(
        "/api/v1/minigames/leaderboard", params={"game": "firefly"}, headers=as_user(player, org)
    )
    assert board.json()["entries"] == []


async def test_a_backlash_win_counts_on_the_game_board_and_no_xp(
    client: AsyncClient, pg_session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both players get their game stats; neither gets XP or skill points."""
    headers = bridge(monkeypatch)
    org, (white, black) = await make_org(pg_session_factory, "White", "Black")
    await _seed_xp(pg_session_factory, org, white)
    room = f"bl-{uuid.uuid4().hex[:12]}"
    body = {
        "matchId": f"{room}:1",
        "roomId": room,
        "orgId": str(org),
        "whiteUserId": str(white),
        "blackUserId": str(black),
        "winnerUserId": str(white),
        "outcome": "win",
        "reason": "all_pieces",
        "moveCount": 40,
        "durationMs": 60_000,
    }
    posted = await client.post(f"{BRIDGE}/backlash-results", json=body, headers=headers)
    assert posted.status_code == 200, posted.text
    replay = await client.post(f"{BRIDGE}/backlash-results", json=body, headers=headers)
    assert replay.json()["recorded"] is False
    stats = {p["userId"]: (p["wins"], p["losses"]) for p in replay.json()["players"]}
    assert stats == {str(white): (1, 0), str(black): (0, 1)}
    await _xp_untouched(pg_session_factory, org, white)
    assert await xp_row(pg_session_factory, org, black) is None


async def test_a_finished_race_writes_placings_and_no_xp(
    client: AsyncClient, pg_session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Race placings land on the race board; the winner's XP is unchanged."""
    headers = bridge(monkeypatch)
    org, (winner, second) = await make_org(pg_session_factory, "Winner", "Second")
    await _seed_xp(pg_session_factory, org, winner)
    placings = [
        {"userId": str(user), "finishTimeMs": ms, "place": place, "finished": True}
        | {"distanceMReached": 100.0, "distanceM": 100}
        for user, ms, place in ((winner, 15_000, 1), (second, 16_000, 2))
    ]
    body = {
        "roomId": f"race-{uuid.uuid4().hex[:8]}",
        "orgId": str(org),
        "hostUserId": str(winner),
        "distanceM": 100,
        "placings": placings,
    }
    posted = await client.post(f"{BRIDGE}/race-results", json=body, headers=headers)
    assert posted.status_code == 200, posted.text
    await _xp_untouched(pg_session_factory, org, winner)
    assert await xp_row(pg_session_factory, org, second) is None
    board = await client.get(
        "/api/v1/races/leaderboard", params={"distance": 100}, headers=as_user(second, org)
    )
    assert [e["userId"] for e in board.json()["entries"]] == [str(winner), str(second)]
