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

"""Unit tests for the mini-game scoring service.

The repository is mocked — these pin the SERVICE contract: game-key
validation, score bounds, that submit_score is XP-free (delegates purely
to MinigameRepository.record_play), and the status/leaderboard shaping.
The streak/best-score mechanics themselves are exercised against a real
session in tests/integration.
"""

import uuid
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.repositories.minigame import LeaderboardRow, PlayOutcome
from app.services.minigame_service import (
    GAMES,
    MinigameValidationError,
    get_leaderboard,
    get_status,
    submit_score,
)

USER_ID = uuid.uuid4()
ORG_ID = uuid.uuid4()


async def test_submit_rejects_unknown_game() -> None:
    db = AsyncMock()
    with pytest.raises(MinigameValidationError, match="unknown game"):
        await submit_score(db, user_id=USER_ID, org_id=ORG_ID, game="chess", score=1)


async def test_submit_rejects_out_of_range_score() -> None:
    db = AsyncMock()
    with pytest.raises(MinigameValidationError, match="score out of range"):
        await submit_score(db, user_id=USER_ID, org_id=ORG_ID, game="fishing", score=1001)


async def test_submit_rejects_score_above_per_game_max() -> None:
    # Anti-tamper: a score within any loose global ceiling but above THIS
    # game's own max must be rejected. Fishing tops out at 50, so 200 (a value
    # a hand-crafted console request could send) is impossible and refused.
    db = AsyncMock()
    assert GAMES["fishing"].max_score == 50
    with pytest.raises(MinigameValidationError, match="score out of range"):
        await submit_score(db, user_id=USER_ID, org_id=ORG_ID, game="fishing", score=200)


async def test_submit_records_play_and_returns_best_streak() -> None:
    db = AsyncMock()
    repo = AsyncMock()
    repo.record_play = AsyncMock(
        return_value=PlayOutcome(
            best_score=42,
            is_new_best=True,
            current_streak=3,
            best_streak=5,
            first_play_today=True,
        )
    )
    with patch("app.services.minigame_service.MinigameRepository", return_value=repo):
        result = await submit_score(db, user_id=USER_ID, org_id=ORG_ID, game="fishing", score=42)

    repo.record_play.assert_awaited_once()
    assert result == {
        "game": "fishing",
        "score": 42,
        "best_score": 42,
        "is_new_best": True,
        "current_streak": 3,
        "best_streak": 5,
        "first_play_today": True,
    }


async def test_submit_is_xp_free() -> None:
    """Regression guard: mini-games must never touch the XP economy."""
    import app.services.minigame_service as svc

    assert not hasattr(svc, "award_xp")
    assert not hasattr(svc, "check_and_award_streak")


async def test_status_reports_best_played_and_live_streak() -> None:
    db = AsyncMock()
    today = date(2026, 6, 12)
    rows = [
        SimpleNamespace(game="fishing", best_score=30, last_played_date=today, current_streak=4),
        SimpleNamespace(
            game="pollen_pop",
            best_score=80,
            last_played_date=today - timedelta(days=5),  # stale streak
            current_streak=9,
        ),
    ]
    repo = AsyncMock()
    repo.list_for_user = AsyncMock(return_value=rows)

    with (
        patch("app.services.minigame_service.MinigameRepository", return_value=repo),
        patch("app.services.minigame_service.datetime") as dt,
    ):
        dt.now.return_value.date.return_value = today
        status = await get_status(db, user_id=USER_ID, org_id=ORG_ID)

    games = {g["key"]: g for g in status["games"]}  # type: ignore[union-attr]
    assert set(games) == set(GAMES)
    assert games["fishing"]["best_score"] == 30
    assert games["fishing"]["played_today"] is True
    assert games["pollen_pop"]["played_today"] is False
    # Only fishing's streak is live (played today); pollen_pop's is stale.
    assert status["streak_count"] == 4


async def test_leaderboard_rejects_unknown_game() -> None:
    db = AsyncMock()
    with pytest.raises(MinigameValidationError, match="unknown game"):
        await get_leaderboard(db, org_id=ORG_ID, game="chess", limit=10)


async def test_leaderboard_passes_through_repo_rows() -> None:
    db = AsyncMock()
    repo = AsyncMock()
    repo.leaderboard = AsyncMock(
        return_value=[
            LeaderboardRow(user_id=USER_ID, user_name="Ada", best_score=48, plays=3),
        ]
    )
    with patch("app.services.minigame_service.MinigameRepository", return_value=repo):
        rows = await get_leaderboard(db, org_id=ORG_ID, game="fishing", limit=10)

    repo.leaderboard.assert_awaited_once_with(game="fishing", limit=10)
    assert rows[0].user_name == "Ada"
    assert rows[0].best_score == 48
