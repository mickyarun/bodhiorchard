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

"""Mini-game scores are capped per game, not by one flat limit on the bridge.

Fishing and Pollen Pop allow up to 6000; the bridge body used to refuse
anything above 1000, so a good run was dropped with a 422 and never counted.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.config import settings
from tests.integration.leave_support import Factory, setup_org

pytestmark = pytest.mark.integration
URL = "/api/v1/internal/colyseus/minigame-results"
SECRET = "cap-test-secret"


def _play(org: uuid.UUID, user: uuid.UUID, game: str, score: int) -> dict[str, object]:
    return {
        "sessionId": f"s-{uuid.uuid4()}",
        "orgId": str(org),
        "userId": str(user),
        "game": game,
        "score": score,
    }


@pytest.mark.parametrize(
    ("game", "score", "expected"),
    [
        ("fishing", 1500, 200),
        ("pollen_pop", 6000, 200),
        ("fishing", 6001, 422),
        ("firefly", 50, 200),
        ("firefly", 51, 422),
        ("firefly", 10**12, 422),
    ],
)
async def test_each_game_has_its_own_ceiling(
    client: AsyncClient,
    pg_session_factory: Factory,
    monkeypatch: pytest.MonkeyPatch,
    game: str,
    score: int,
    expected: int,
) -> None:
    """Scores up to the game's own maximum are recorded; above it, refused."""
    monkeypatch.setattr(settings.colyseus, "bridge_secret", SECRET)
    org, (player,), _ = await setup_org(pg_session_factory, "Player")
    body = _play(org, player, game, score)
    response = await client.post(URL, json=body, headers={"X-Bridge-Secret": SECRET})
    assert response.status_code == expected, response.text
    if expected == 200:
        assert response.json()["best_score"] == score
