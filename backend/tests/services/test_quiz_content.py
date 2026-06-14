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

"""Unit tests for pure quiz-content helpers (no DB)."""

import pytest

from app.models.quiz_question import QuizQuestionType
from app.schemas.quiz import GeneratedQuestion
from app.services.quiz_content import (
    normalize_text,
    topic_hash,
    validate_question_content,
)


class TestNormalizeText:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("  Hello,  World! ", "hello world"),
            ("FastAPI.", "fastapi"),
            ("multi   space", "multi space"),
            ("Don't", "dont"),
        ],
    )
    def test_normalization(self, raw: str, expected: str) -> None:
        assert normalize_text(raw) == expected


class TestTopicHash:
    def test_stable_and_case_insensitive(self) -> None:
        assert topic_hash("BUD:BUD-012:Owner") == topic_hash("bud:bud-012:owner  ")

    def test_distinct_topics_differ(self) -> None:
        assert topic_hash("feature:slack") != topic_hash("feature:github")


class TestValidateMultipleChoice:
    def test_valid(self) -> None:
        validate_question_content(
            QuizQuestionType.MULTIPLE_CHOICE,
            {"choices": ["a", "b", "c", "d"]},
            {"correct_index": 2},
        )

    @pytest.mark.parametrize(
        ("payload", "answer_key"),
        [
            ({"choices": ["only"]}, {"correct_index": 0}),  # too few
            ({"choices": ["a", "b"]}, {"correct_index": 5}),  # out of range
            ({"choices": ["a", "b"]}, {"correct_index": True}),  # bool, not int
            ({"choices": ["a", ""]}, {"correct_index": 0}),  # empty choice
            ({}, {"correct_index": 0}),  # no choices
        ],
    )
    def test_invalid(self, payload: dict, answer_key: dict) -> None:
        with pytest.raises(ValueError):
            validate_question_content(QuizQuestionType.MULTIPLE_CHOICE, payload, answer_key)


class TestValidateScramble:
    def test_valid_rearrangement(self) -> None:
        validate_question_content(
            QuizQuestionType.SCRAMBLE,
            {"scrambled": "aato", "kind": "letters"},
            {"answer": "atoa"},
        )

    def test_rejects_non_rearrangement(self) -> None:
        with pytest.raises(ValueError):
            validate_question_content(
                QuizQuestionType.SCRAMBLE,
                {"scrambled": "xyz"},
                {"answer": "atoa"},
            )

    def test_rejects_empty_answer(self) -> None:
        with pytest.raises(ValueError):
            validate_question_content(
                QuizQuestionType.SCRAMBLE, {"scrambled": "ab"}, {"answer": ""}
            )


class TestValidateFillBlank:
    def test_valid_with_aliases(self) -> None:
        validate_question_content(
            QuizQuestionType.FILL_BLANK,
            {"hint": "a web framework"},
            {"answer": "FastAPI", "aliases": ["fast api"]},
        )

    def test_rejects_empty_answer(self) -> None:
        with pytest.raises(ValueError):
            validate_question_content(QuizQuestionType.FILL_BLANK, {}, {"answer": "  "})

    def test_rejects_non_string_aliases(self) -> None:
        with pytest.raises(ValueError):
            validate_question_content(
                QuizQuestionType.FILL_BLANK, {}, {"answer": "x", "aliases": [1, 2]}
            )


class TestGeneratedQuestionValidation:
    """The Pydantic model must reject content-inconsistent questions at parse time."""

    def test_valid_question_parses(self) -> None:
        q = GeneratedQuestion(
            question_type=QuizQuestionType.MULTIPLE_CHOICE,
            prompt="Which feature shipped first?",
            payload={"choices": ["A", "B", "C", "D"]},
            answer_key={"correct_index": 1},
            topic_key="feature:first",
        )
        assert q.question_type == QuizQuestionType.MULTIPLE_CHOICE

    def test_bad_content_rejected(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            GeneratedQuestion(
                question_type=QuizQuestionType.MULTIPLE_CHOICE,
                prompt="Bad",
                payload={"choices": ["A", "B"]},
                answer_key={"correct_index": 9},
                topic_key="x",
            )
