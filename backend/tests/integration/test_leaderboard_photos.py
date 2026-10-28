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

"""Every leaderboard carries each person's stored ``avatar_url``.

Runs the real handlers against Postgres, so the repository ``SELECT`` and
the response serialisation (camelCase on the race and quiz boards) are
both exercised. One player has a photo and one doesn't.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.v1 import minigames, quiz, races
from app.models.backlash import BacklashPlayerStats
from app.models.minigame import MinigameScore
from app.models.organization import Organization
from app.models.quiz_score import QuizScore
from app.models.race_result import RaceResult
from app.models.user import OrgToUser, User
from app.services.minigame_service import BACKLASH_GAME_KEY, GAMES

pytestmark = pytest.mark.integration

PHOTO = "/api/v1/employees/avatars/0123456789abcdef0123456789abcdef"
MONTH = "2026-10"


async def _seed(factory: async_sessionmaker[AsyncSession]) -> SimpleNamespace:
    """An org with a photographed leader and a runner-up without a photo."""
    async with factory() as db:
        org = Organization(name=f"Board {uuid.uuid4()}", slug=f"b-{uuid.uuid4().hex[:8]}")
        db.add(org)
        await db.flush()
        users = []
        for name, avatar in (("Asha Rao", PHOTO), ("Ben Okafor", None)):
            user = User(
                email=f"{uuid.uuid4().hex[:8]}@example.com",
                name=name,
                password_hash="x",
                avatar_url=avatar,
            )
            db.add(user)
            await db.flush()
            db.add(OrgToUser(user_id=user.id, org_id=org.id))
            users.append(user)
        game = next(iter(GAMES))
        for rank, user in enumerate(users):
            db.add(
                RaceResult(
                    room_id=f"room-{uuid.uuid4().hex[:6]}",
                    org_id=org.id,
                    user_id=user.id,
                    host_user_id=users[0].id,
                    distance_m=100,
                    finish_time_ms=10_000 + rank,
                    place=rank + 1,
                    finished=True,
                    distance_m_reached=100.0,
                    finished_at=datetime.now(UTC),
                )
            )
            db.add(
                MinigameScore(
                    org_id=org.id, user_id=user.id, game=game, best_score=50 - rank, plays=1
                )
            )
            db.add(
                BacklashPlayerStats(
                    org_id=org.id, user_id=user.id, wins=5 - rank, losses=1 + rank, matches=6
                )
            )
            db.add(
                QuizScore(
                    org_id=org.id,
                    user_id=user.id,
                    period_month=MONTH,
                    total_points=100 - rank,
                    correct_count=3,
                    total_answered=3,
                )
            )
        await db.commit()
        return SimpleNamespace(org_id=org.id, id=users[0].id, game=game)


def _photos(entries: list[dict[str, Any]], key: str) -> list[Any]:
    return [e[key] for e in entries]


async def test_race_board_returns_photos(
    pg_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    me = await _seed(pg_session_factory)
    async with pg_session_factory() as db:
        board = await races.get_race_leaderboard(distance=100, limit=10, current_user=me, db=db)
    body = board.model_dump(by_alias=True)
    assert _photos(body["entries"], "avatarUrl") == [PHOTO, None]


@pytest.mark.parametrize("which", ["score", "backlash"])
async def test_minigame_board_returns_photos(
    pg_session_factory: async_sessionmaker[AsyncSession], which: str
) -> None:
    me = await _seed(pg_session_factory)
    game = me.game if which == "score" else BACKLASH_GAME_KEY
    async with pg_session_factory() as db:
        board = await minigames.minigame_leaderboard(game=game, limit=10, current_user=me, db=db)
    assert _photos(board.model_dump()["entries"], "avatar_url") == [PHOTO, None]


async def test_quiz_board_returns_photos(
    pg_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    me = await _seed(pg_session_factory)
    async with pg_session_factory() as db:
        rows = await quiz.get_monthly_leaderboard(month=MONTH, limit=10, current_user=me, db=db)
    body = [r.model_dump(by_alias=True) for r in rows]
    assert _photos(body, "avatarUrl") == [PHOTO, None]
