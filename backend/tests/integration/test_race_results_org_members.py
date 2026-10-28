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

"""Race results keep only members of the org they are posted for.

The mini-game, Backlash and race-invite bridge writes all check membership;
race results did not, so another org's user could land on this org's race
board with their name showing.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.config import settings
from app.models.race_result import RaceResult
from tests.integration.leave_support import Factory, as_user, give_role, setup_org

pytestmark = pytest.mark.integration
URL = "/api/v1/internal/colyseus/race-results"
SECRET = "race-test-secret"


def _body(org: uuid.UUID, host: uuid.UUID, *racers: uuid.UUID) -> dict[str, object]:
    return {
        "roomId": f"race-{uuid.uuid4().hex[:8]}",
        "orgId": str(org),
        "hostUserId": str(host),
        "distanceM": 100,
        "placings": [
            {
                "userId": str(user),
                "finishTimeMs": 15_000 + place,
                "place": place,
                "finished": True,
                "distanceMReached": 100.0,
                "distanceM": 100,
            }
            for place, user in enumerate(racers, start=1)
        ],
    }


async def test_an_outsiders_row_is_dropped_and_the_members_rows_are_kept(
    client: AsyncClient, pg_session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The board shows host and racer; the other org's racer is never stored."""
    monkeypatch.setattr(settings.colyseus, "bridge_secret", SECRET)
    org, (host, racer), _ = await setup_org(pg_session_factory, "Host", "Racer")
    _other, (outsider,), _ = await setup_org(pg_session_factory, "Outsider")
    await give_role(pg_session_factory, org, racer, "developer")
    body = _body(org, host, host, outsider, racer)
    posted = await client.post(URL, json=body, headers={"X-Bridge-Secret": SECRET})
    assert posted.status_code == 200, posted.text
    assert posted.json() == {"rowsWritten": 2}
    board = await client.get(
        "/api/v1/races/leaderboard", params={"distance": 100}, headers=as_user(racer, org)
    )
    assert [e["userId"] for e in board.json()["entries"]] == [str(host), str(racer)]
    async with pg_session_factory() as db:
        stored = await db.scalars(select(RaceResult.user_id).where(RaceResult.org_id == org))
        assert set(stored) == {host, racer}


async def test_a_race_of_only_outsiders_writes_nothing(
    client: AsyncClient, pg_session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No member placings means no rows, and the call still succeeds."""
    monkeypatch.setattr(settings.colyseus, "bridge_secret", SECRET)
    org, (host,), _ = await setup_org(pg_session_factory, "Host")
    _other, (outsider,), _ = await setup_org(pg_session_factory, "Outsider")
    posted = await client.post(
        URL, json=_body(org, host, outsider), headers={"X-Bridge-Secret": SECRET}
    )
    assert posted.status_code == 200 and posted.json() == {"rowsWritten": 0}
    async with pg_session_factory() as db:
        stored = await db.scalars(select(RaceResult.user_id).where(RaceResult.org_id == org))
        assert list(stored) == []
