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

"""Tests for the mini-game Slack nudge composer.

``compose_digest`` is a pure function — these pin the nudge logic
(streak-at-risk, leaderboard nudge, leader suppression, empty result)
without any Slack/DB I/O. The send/sweep plumbing reuses the proven
race-invite Slack seam and the velocity-roller loop, both already tested.
"""

import uuid
from datetime import date, timedelta

from app.repositories.minigame import LeaderboardRow
from app.services.minigame_nudge import _UserGameState, compose_digest

ME = uuid.uuid4()
RIVAL = uuid.uuid4()
TODAY = date(2026, 6, 12)
YESTERDAY = TODAY - timedelta(days=1)
FRONTEND = "https://app.example.test"


def _leaders(**kw: LeaderboardRow | None) -> dict[str, LeaderboardRow | None]:
    # Default: nobody leads either game.
    base: dict[str, LeaderboardRow | None] = {"fishing": None, "pollen_pop": None}
    base.update(kw)
    return base


def test_streak_at_risk_is_nudged() -> None:
    states = [
        _UserGameState(game="fishing", best_score=20, current_streak=4, last_played_date=YESTERDAY)
    ]
    msg = compose_digest(
        user_id=ME,
        user_name="Me",
        states=states,
        leaders=_leaders(),
        today=TODAY,
        frontend_url=FRONTEND,
    )
    assert msg is not None
    assert "4-day" in msg
    assert "keep your" in msg.lower()


def test_leader_nudge_when_someone_else_is_ahead() -> None:
    leaders = _leaders(
        fishing=LeaderboardRow(user_id=RIVAL, user_name="Ada", best_score=48, plays=2)
    )
    states = [
        _UserGameState(game="fishing", best_score=30, current_streak=1, last_played_date=TODAY)
    ]
    msg = compose_digest(
        user_id=ME,
        user_name="Me",
        states=states,
        leaders=leaders,
        today=TODAY,
        frontend_url=FRONTEND,
    )
    assert msg is not None
    assert "Ada" in msg
    assert "48" in msg
    assert "your best is 30" in msg


def test_no_nudge_when_user_already_leads_and_played_today() -> None:
    leaders = _leaders(
        fishing=LeaderboardRow(user_id=ME, user_name="Me", best_score=48, plays=2),
        pollen_pop=LeaderboardRow(user_id=ME, user_name="Me", best_score=90, plays=1),
    )
    states = [
        _UserGameState(game="fishing", best_score=48, current_streak=3, last_played_date=TODAY),
        _UserGameState(game="pollen_pop", best_score=90, current_streak=3, last_played_date=TODAY),
    ]
    msg = compose_digest(
        user_id=ME,
        user_name="Me",
        states=states,
        leaders=leaders,
        today=TODAY,
        frontend_url=FRONTEND,
    )
    assert msg is None


def test_empty_game_invites_first_player() -> None:
    msg = compose_digest(
        user_id=ME,
        user_name="Me",
        states=[],
        leaders=_leaders(),
        today=TODAY,
        frontend_url=FRONTEND,
    )
    assert msg is not None
    assert "claim the top spot" in msg.lower()
    assert msg.count("\n") >= 2  # header + at least one line + footer


def test_streak_takes_priority_over_leaderboard_for_same_game() -> None:
    # Same game is both streak-at-risk AND led by a rival — streak wins
    # (only one line per game), so the rival nudge is suppressed.
    leaders = _leaders(
        fishing=LeaderboardRow(user_id=RIVAL, user_name="Ada", best_score=99, plays=5)
    )
    states = [
        _UserGameState(game="fishing", best_score=10, current_streak=6, last_played_date=YESTERDAY)
    ]
    msg = compose_digest(
        user_id=ME,
        user_name="Me",
        states=states,
        leaders=leaders,
        today=TODAY,
        frontend_url=FRONTEND,
    )
    assert msg is not None
    assert "6-day" in msg
    assert "Ada" not in msg.split("pollen", 1)[0]  # no fishing leader line
