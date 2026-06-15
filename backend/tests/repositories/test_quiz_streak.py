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

"""Unit tests for the pure quiz-day streak math.

Extracted from ``QuizScoreRepository.record`` so the branching is testable
without a live DB (the suite deliberately avoids real-DB fixtures).
"""

from datetime import date

from app.repositories.quiz_score import compute_streak_advance


def _advance(
    *,
    prev_participation: int = 0,
    prev_correct: int = 0,
    prev_best: int = 0,
    last_quiz_date: date | None = None,
    prev_quiz_date: date | None = None,
    is_correct: bool = True,
):
    return compute_streak_advance(
        prev_participation=prev_participation,
        prev_correct=prev_correct,
        prev_best=prev_best,
        last_quiz_date=last_quiz_date,
        prev_quiz_date=prev_quiz_date,
        is_correct=is_correct,
    )


class TestParticipationStreak:
    def test_first_ever_quiz_starts_at_one(self) -> None:
        # No prior participation, org had no previous quiz.
        a = _advance(last_quiz_date=None, prev_quiz_date=None)
        assert a.participation_streak == 1

    def test_continuity_increments(self) -> None:
        # User last answered the org's immediately-preceding quiz (Mon),
        # now answering the next one (Fri) — streak continues.
        a = _advance(
            prev_participation=3,
            last_quiz_date=date(2026, 6, 1),
            prev_quiz_date=date(2026, 6, 1),
        )
        assert a.participation_streak == 4

    def test_gap_resets_to_one(self) -> None:
        # User's last answered quiz is NOT the org's previous quiz — they
        # missed one, so the streak resets.
        a = _advance(
            prev_participation=5,
            last_quiz_date=date(2026, 5, 25),
            prev_quiz_date=date(2026, 6, 1),
        )
        assert a.participation_streak == 1


class TestCorrectStreak:
    def test_wrong_answer_resets_correct_streak(self) -> None:
        a = _advance(
            prev_correct=4,
            last_quiz_date=date(2026, 6, 1),
            prev_quiz_date=date(2026, 6, 1),
            is_correct=False,
        )
        assert a.correct_streak == 0
        # Participation still advances even on a wrong answer.
        assert a.participation_streak >= 1

    def test_correct_with_continuity_increments(self) -> None:
        a = _advance(
            prev_correct=2,
            last_quiz_date=date(2026, 6, 1),
            prev_quiz_date=date(2026, 6, 1),
            is_correct=True,
        )
        assert a.correct_streak == 3

    def test_correct_after_gap_resets_to_one(self) -> None:
        a = _advance(
            prev_correct=9,
            last_quiz_date=date(2026, 5, 1),
            prev_quiz_date=date(2026, 6, 1),
            is_correct=True,
        )
        assert a.correct_streak == 1

    def test_recover_correct_after_previous_wrong(self) -> None:
        # Previously wrong (correct streak was 0) but participation continuous,
        # now correct → correct streak becomes 1.
        a = _advance(
            prev_participation=4,
            prev_correct=0,
            last_quiz_date=date(2026, 6, 1),
            prev_quiz_date=date(2026, 6, 1),
            is_correct=True,
        )
        assert a.correct_streak == 1


class TestBestStreak:
    def test_best_tracks_high_water_mark(self) -> None:
        a = _advance(
            prev_participation=6,
            prev_best=6,
            last_quiz_date=date(2026, 6, 1),
            prev_quiz_date=date(2026, 6, 1),
        )
        assert a.best_streak == 7

    def test_best_unchanged_when_streak_resets(self) -> None:
        a = _advance(
            prev_participation=8,
            prev_best=8,
            last_quiz_date=date(2026, 5, 1),
            prev_quiz_date=date(2026, 6, 1),
        )
        assert a.participation_streak == 1
        assert a.best_streak == 8
