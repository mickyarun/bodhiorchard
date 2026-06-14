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

"""Unit tests for monthly champion selection (pure) — incl. tie-splitting."""

import uuid

from app.repositories.quiz_score import MonthlyLeaderboardRow
from app.services.quiz_monthly_rollup import select_winners

A, B, C = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()


def _row(uid: uuid.UUID, points: int, correct: int, time_ms: int) -> MonthlyLeaderboardRow:
    return MonthlyLeaderboardRow(
        user_id=uid,
        user_name=str(uid),
        total_points=points,
        correct_count=correct,
        total_time_ms=time_ms,
    )


def test_single_clear_winner() -> None:
    rows = [_row(A, 300, 3, 1000), _row(B, 200, 2, 900)]
    assert select_winners(rows, {A, B}) == [A]


def test_more_correct_breaks_point_tie_single_winner() -> None:
    # Same points, A has more correct → A alone wins (no split).
    rows = [_row(A, 300, 3, 5000), _row(B, 300, 2, 1000)]
    assert select_winners(rows, {A, B}) == [A]


def test_faster_breaks_tie_single_winner() -> None:
    # Same points + correct, A faster → A alone (no split).
    rows = [_row(A, 300, 3, 1000), _row(B, 300, 3, 2000)]
    assert select_winners(rows, {A, B}) == [A]


def test_true_tie_splits() -> None:
    # Identical points + correct + time → both win, prize is split.
    rows = [_row(A, 300, 3, 1500), _row(B, 300, 3, 1500), _row(C, 100, 1, 9000)]
    winners = select_winners(rows, {A, B, C})
    assert set(winners) == {A, B}
    assert len(winners) == 2


def test_inactive_top_scorer_rolls_to_next_active() -> None:
    # A has the top score but is inactive → B (next active) wins.
    rows = [_row(A, 500, 5, 1000), _row(B, 300, 3, 1000)]
    assert select_winners(rows, {B}) == [B]


def test_zero_points_no_winner() -> None:
    rows = [_row(A, 0, 0, 1000), _row(B, 0, 0, 2000)]
    assert select_winners(rows, {A, B}) == []


def test_empty_rows() -> None:
    assert select_winners([], set()) == []
