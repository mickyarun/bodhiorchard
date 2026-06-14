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

"""Unit tests for per-type grading and the scoring formula (pure)."""

from app.models.quiz_question import QuizQuestionType
from app.services.quiz_constants import (
    BASE_POINTS,
    MAX_SPEED_BONUS,
    score_for_answer,
    speed_bonus,
)
from app.services.quiz_grading import grade


class TestMultipleChoiceGrading:
    KEY = {"correct_index": 2}

    def test_correct_index(self) -> None:
        assert grade(QuizQuestionType.MULTIPLE_CHOICE, {"index": 2}, self.KEY) is True

    def test_wrong_index(self) -> None:
        assert grade(QuizQuestionType.MULTIPLE_CHOICE, {"index": 0}, self.KEY) is False

    def test_bool_index_rejected(self) -> None:
        # True == 1 in Python; must not be accepted as an index.
        assert (
            grade(QuizQuestionType.MULTIPLE_CHOICE, {"index": True}, {"correct_index": 1}) is False
        )

    def test_missing_index(self) -> None:
        assert grade(QuizQuestionType.MULTIPLE_CHOICE, {}, self.KEY) is False


class TestScrambleGrading:
    KEY = {"answer": "FastAPI"}

    def test_case_insensitive_match(self) -> None:
        assert grade(QuizQuestionType.SCRAMBLE, {"text": "fastapi"}, self.KEY) is True

    def test_wrong(self) -> None:
        assert grade(QuizQuestionType.SCRAMBLE, {"text": "django"}, self.KEY) is False


class TestFillBlankGrading:
    KEY = {"answer": "PostgreSQL", "aliases": ["postgres", "psql"]}

    def test_canonical(self) -> None:
        assert grade(QuizQuestionType.FILL_BLANK, {"text": "  postgresql "}, self.KEY) is True

    def test_alias(self) -> None:
        assert grade(QuizQuestionType.FILL_BLANK, {"text": "Postgres"}, self.KEY) is True

    def test_punctuation_tolerant(self) -> None:
        assert grade(QuizQuestionType.FILL_BLANK, {"text": "psql!"}, self.KEY) is True

    def test_wrong(self) -> None:
        assert grade(QuizQuestionType.FILL_BLANK, {"text": "mysql"}, self.KEY) is False

    def test_empty_rejected(self) -> None:
        assert grade(QuizQuestionType.FILL_BLANK, {"text": "   "}, self.KEY) is False


class TestScoreFormula:
    def test_wrong_answer_zero(self) -> None:
        assert score_for_answer(is_correct=False, latency_ms=0, grace_minutes=60) == 0

    def test_instant_correct_full_bonus(self) -> None:
        assert score_for_answer(is_correct=True, latency_ms=0, grace_minutes=60) == (
            BASE_POINTS + MAX_SPEED_BONUS
        )

    def test_after_grace_no_bonus(self) -> None:
        # Answered well after the grace window → base only.
        ms = 2 * 60 * 60 * 1000  # 2h, grace is 60m
        assert score_for_answer(is_correct=True, latency_ms=ms, grace_minutes=60) == BASE_POINTS

    def test_bonus_decays_monotonically(self) -> None:
        early = speed_bonus(5 * 60 * 1000, 60)  # 5 min in
        late = speed_bonus(45 * 60 * 1000, 60)  # 45 min in
        assert MAX_SPEED_BONUS >= early > late >= 0

    def test_zero_grace_gives_full_bonus_only_at_open(self) -> None:
        assert speed_bonus(0, 0) == MAX_SPEED_BONUS  # answered at open → full
        assert speed_bonus(1000, 0) == 0  # no grace window → no bonus after open
