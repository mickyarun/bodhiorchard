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

"""Unit tests for the competitive Slack message composers (pure)."""

from app.services.quiz_notify import compose_open_message, compose_reveal_message

LINK = "https://app.example/dashboard"


class TestOpenMessage:
    def test_names_the_leader_to_beat(self) -> None:
        msg = compose_open_message(LINK, [("Alice", 420), ("Bob", 380)], 1.0)
        assert "Alice" in msg and "420" in msg
        assert "top the board" in msg
        assert LINK in msg

    def test_advertises_sp_prize(self) -> None:
        msg = compose_open_message(LINK, [], 2.0)
        assert "2 SP" in msg  # %g drops the trailing .0
        assert "Monthly prize" in msg

    def test_explains_scoring_rules(self) -> None:
        from app.services.quiz_constants import BASE_POINTS, MAX_SPEED_BONUS

        msg = compose_open_message(LINK, [], 1.0)
        assert "How it scores" in msg
        assert str(BASE_POINTS) in msg  # base points
        assert f"+{MAX_SPEED_BONUS}" in msg  # speed bonus

    def test_no_sp_line_when_amount_zero(self) -> None:
        msg = compose_open_message(LINK, [("Alice", 10)], 0)
        # Scoring rules still show, but no monthly-prize line.
        assert "Monthly prize" not in msg
        assert "How it scores" in msg

    def test_empty_board_invites_first_score(self) -> None:
        msg = compose_open_message(LINK, [], 1.0)
        assert "first" in msg.lower()
        assert "Alice" not in msg

    def test_all_zero_treated_as_empty(self) -> None:
        # A member on the board with 0 pts isn't a "leader to beat".
        msg = compose_open_message(LINK, [("Arun", 0)], 1.0)
        assert "first" in msg.lower()
        assert "leads" not in msg


class TestRevealMessage:
    def test_lists_top_three_with_medals(self) -> None:
        msg = compose_reveal_message(LINK, [("Alice", 420), ("Bob", 380), ("Cara", 300)])
        assert "🥇 Alice" in msg
        assert "🥈 Bob" in msg
        assert "🥉 Cara" in msg
        assert LINK in msg

    def test_no_standings_block_when_board_empty(self) -> None:
        msg = compose_reveal_message(LINK, [])
        assert "leaders" not in msg.lower()
        assert "answer is in" in msg.lower()

    def test_zero_point_rows_excluded(self) -> None:
        msg = compose_reveal_message(LINK, [("Arun", 0)])
        assert "Arun" not in msg
        assert "leaders" not in msg.lower()
