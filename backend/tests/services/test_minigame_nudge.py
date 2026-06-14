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
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.repositories.minigame import LeaderboardRow
from app.services.minigame_nudge import (
    _due_local_date,
    _UserGameState,
    _zone_for_config,
    compose_digest,
)
from app.services.minigame_service import GAMES

ME = uuid.uuid4()
RIVAL = uuid.uuid4()
TODAY = date(2026, 6, 12)
YESTERDAY = TODAY - timedelta(days=1)
FRONTEND = "https://app.example.test"


def _leaders(**kw: LeaderboardRow | None) -> dict[str, LeaderboardRow | None]:
    # Default: nobody leads any game. Derived from the registry so adding a
    # game doesn't silently leave a key unaccounted for.
    base: dict[str, LeaderboardRow | None] = dict.fromkeys(GAMES, None)
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
    # The user already tops EVERY registered game and played each today — no
    # streak at risk, no rival ahead, nothing unplayed — so the digest is
    # silent. Built from GAMES so a newly-added game can't reopen a nudge.
    leaders = _leaders(
        **{g: LeaderboardRow(user_id=ME, user_name="Me", best_score=50, plays=2) for g in GAMES}
    )
    states = [
        _UserGameState(game=g, best_score=50, current_streak=3, last_played_date=TODAY)
        for g in GAMES
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


# ── Scheduling: 09:00 in the org's own timezone ──


def _cfg(tz: str | None) -> dict | None:
    return {"presence": {"timezone": tz}} if tz else None


def test_zone_resolves_iana_name() -> None:
    assert _zone_for_config(_cfg("America/New_York")) == ZoneInfo("America/New_York")


def test_zone_falls_back_to_none_when_unset_or_invalid() -> None:
    assert _zone_for_config(None) is None
    assert _zone_for_config({"presence": {}}) is None
    # An invalid IANA name is rejected by presence validation → default (None).
    assert _zone_for_config({"presence": {"timezone": "Mars/Olympus"}}) is None


def test_due_at_local_9am_returns_local_date() -> None:
    # 09:30 IST (UTC+5:30) == 04:00 UTC.
    now_utc = datetime(2026, 6, 12, 4, 0, tzinfo=UTC)
    due = _due_local_date(config=_cfg("Asia/Kolkata"), now_utc=now_utc, last_nudged_local=None)
    assert due == date(2026, 6, 12)


def test_not_due_outside_the_9am_hour() -> None:
    # 10:30 IST == 05:00 UTC — past the 09:00 window.
    now_utc = datetime(2026, 6, 12, 5, 0, tzinfo=UTC)
    assert (
        _due_local_date(config=_cfg("Asia/Kolkata"), now_utc=now_utc, last_nudged_local=None)
        is None
    )


def test_not_due_when_already_nudged_today() -> None:
    now_utc = datetime(2026, 6, 12, 4, 0, tzinfo=UTC)  # 09:30 IST
    assert (
        _due_local_date(
            config=_cfg("Asia/Kolkata"),
            now_utc=now_utc,
            last_nudged_local=date(2026, 6, 12),
        )
        is None
    )


def test_each_org_fires_at_its_own_local_9am() -> None:
    # Same instant: 09:30 in Kolkata is 00:00 in New York — only Kolkata is due.
    now_utc = datetime(2026, 6, 12, 4, 0, tzinfo=UTC)
    assert (
        _due_local_date(config=_cfg("Asia/Kolkata"), now_utc=now_utc, last_nudged_local=None)
        is not None
    )
    assert (
        _due_local_date(config=_cfg("America/New_York"), now_utc=now_utc, last_nudged_local=None)
        is None
    )
