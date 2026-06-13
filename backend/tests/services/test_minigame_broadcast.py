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

"""Tests for the mini-game high-score broadcast.

``is_new_org_record`` and ``compose_high_score_announcement`` are pure — these
pin the dethrone rule (beat a DIFFERENT player's standing record) and the
announcement text without any Slack/DB I/O.
"""

import uuid

from app.repositories.minigame import LeaderboardRow
from app.services.minigame_broadcast import (
    compose_high_score_announcement,
    is_new_org_record,
)

ME = uuid.uuid4()
RIVAL = uuid.uuid4()
FRONTEND = "https://app.example.test"


def _row(user_id: uuid.UUID, best: int) -> LeaderboardRow:
    return LeaderboardRow(user_id=user_id, user_name="Ada", best_score=best, plays=3)


def test_dethroning_a_rival_with_a_higher_score_is_a_record() -> None:
    assert is_new_org_record(prev_top=_row(RIVAL, 45), breaker_id=ME, score=46) is True


def test_padding_your_own_lead_is_not_a_record() -> None:
    # Same player already holds the top — improving it shouldn't notify everyone.
    assert is_new_org_record(prev_top=_row(ME, 45), breaker_id=ME, score=99) is False


def test_not_beating_the_standing_score_is_not_a_record() -> None:
    assert is_new_org_record(prev_top=_row(RIVAL, 45), breaker_id=ME, score=45) is False
    assert is_new_org_record(prev_top=_row(RIVAL, 45), breaker_id=ME, score=30) is False


def test_announcement_names_the_breaker_old_holder_and_scores() -> None:
    msg = compose_high_score_announcement(
        breaker_name="Arun",
        game_name="Lake Fishing",
        score=50,
        previous_best=45,
        previous_holder="Ada",
        frontend_url=FRONTEND,
    )
    assert "Arun" in msg
    assert "Lake Fishing" in msg
    assert "50" in msg
    assert "Ada" in msg
    assert "45" in msg
    assert msg.startswith("🏆")
    assert f"{FRONTEND}/dashboard" in msg


def test_announcement_falls_back_when_breaker_name_is_blank() -> None:
    msg = compose_high_score_announcement(
        breaker_name="  ",
        game_name="Pollen Pop",
        score=120,
        previous_best=88,
        previous_holder="Ada",
        frontend_url=FRONTEND,
    )
    assert "Someone" in msg
