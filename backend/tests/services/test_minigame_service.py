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

XP/streak plumbing (award_xp / check_and_award_streak) is mocked — those
have their own coverage. These tests pin the service contract: game-key
validation, score bounds, XP composition, dedup passthrough, and that a
replayed game still ticks the daily streak.
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.services.minigame_service import (
    GAMES,
    MinigameValidationError,
    get_status,
    submit_score,
)
from app.services.xp_service import XPAwardResult

USER_ID = uuid.uuid4()
ORG_ID = uuid.uuid4()


def _award(amount: int = 35) -> XPAwardResult:
    return XPAwardResult(
        amount_awarded=amount,
        new_total=100,
        old_level=1,
        new_level=1,
        level_changed=False,
        new_level_name="Sprout",
    )


async def test_submit_rejects_unknown_game() -> None:
    db = AsyncMock()
    with pytest.raises(MinigameValidationError, match="unknown game"):
        await submit_score(db, user_id=USER_ID, org_id=ORG_ID, game="chess", score=1)


async def test_submit_rejects_out_of_range_score() -> None:
    db = AsyncMock()
    with pytest.raises(MinigameValidationError, match="score out of range"):
        await submit_score(db, user_id=USER_ID, org_id=ORG_ID, game="fishing", score=1001)


async def test_submit_awards_base_plus_capped_score_bonus() -> None:
    db = AsyncMock()
    with (
        patch(
            "app.services.minigame_service.award_xp", new=AsyncMock(return_value=_award())
        ) as award,
        patch(
            "app.services.minigame_service.check_and_award_streak",
            new=AsyncMock(return_value=3),
        ),
    ):
        result = await submit_score(db, user_id=USER_ID, org_id=ORG_ID, game="fishing", score=900)

    # base 15 + bonus capped at 35 → 50, regardless of a 900 score
    assert award.call_args.kwargs["amount"] == 50.0
    assert award.call_args.kwargs["source"] == "minigame"
    assert "fishing" in award.call_args.kwargs["source_ref"]
    assert result["first_play_today"] is True
    assert result["xp_awarded"] == 35
    assert result["streak_count"] == 3


async def test_replay_is_deduped_but_still_ticks_streak() -> None:
    db = AsyncMock()
    with (
        patch("app.services.minigame_service.award_xp", new=AsyncMock(return_value=None)),
        patch(
            "app.services.minigame_service.check_and_award_streak",
            new=AsyncMock(return_value=5),
        ) as streak,
    ):
        result = await submit_score(
            db, user_id=USER_ID, org_id=ORG_ID, game="pollen_pop", score=10
        )

    assert result["first_play_today"] is False
    assert result["xp_awarded"] == 0
    assert result["total_xp"] is None
    assert result["streak_count"] == 5
    streak.assert_awaited_once()


async def test_status_reports_per_game_play_state_and_streak() -> None:
    db = AsyncMock()
    event_repo = AsyncMock()
    event_repo.has_source_ref = AsyncMock(side_effect=[True, False])
    xp_repo = AsyncMock()
    xp_row = type("Row", (), {"streak_count": 4, "streak_best": 9})()
    xp_repo.get_by_user = AsyncMock(return_value=xp_row)

    with (
        patch(
            "app.services.minigame_service.RewardEventRepository",
            return_value=event_repo,
        ),
        patch(
            "app.services.minigame_service.DeveloperXPRepository",
            return_value=xp_repo,
        ),
    ):
        status = await get_status(db, user_id=USER_ID, org_id=ORG_ID)

    games = {g["key"]: g for g in status["games"]}  # type: ignore[union-attr]
    assert set(games) == set(GAMES)
    assert status["streak_count"] == 4
    assert status["streak_best"] == 9
    played = [g["played_today"] for g in status["games"]]  # type: ignore[union-attr]
    assert played == [True, False]
