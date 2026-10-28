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

"""A quiz question must not show its own answer in the prompt or payload.

Covers the generated-draft parse (``GeneratedQuestion``) and the admin edit
(``edit_question``), the two places a question enters or changes in the pool.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.models.quiz_question import QuizQuestionType
from app.schemas.quiz import GeneratedQuestion, QuizReviewEdit
from app.services import quiz_review
from app.services.quiz_review import edit_question

MCQ = {"choices": ["Redis", "Kafka", "Postgres", "SQS"]}

GIVEAWAYS: list[tuple[str, str, dict[str, Any], dict[str, Any]]] = [
    ("scramble", "Unscramble our cache layer", {"scrambled": "Redis"}, {"answer": "redis"}),
    ("scramble", "Unscramble Redis, the cache", {"scrambled": "sdire"}, {"answer": "redis"}),
    ("fill_blank", "Postgres is the ____ we run.", {"hint": "a db"}, {"answer": "Postgres"}),
    (
        "fill_blank",
        "Our main database is ____.",
        {"hint": "rhymes with pg"},
        {"answer": "postgres", "aliases": ["PG"]},
    ),
    ("multiple_choice", "Redis backs the queue. Which store is it?", MCQ, {"correct_index": 0}),
]

FAIR: list[tuple[str, str, dict[str, Any], dict[str, Any]]] = [
    ("scramble", "Unscramble our cache layer", {"scrambled": "sdire"}, {"answer": "redis"}),
    ("fill_blank", "The ____ toolchain keeps going strong.", {"hint": "short"}, {"answer": "Go"}),
    ("multiple_choice", "Redis or Kafka: which backs the queue?", MCQ, {"correct_index": 0}),
]


def _generated(qtype: str, prompt: str, payload: dict[str, Any], key: dict[str, Any]) -> Any:
    return GeneratedQuestion(
        question_type=QuizQuestionType(qtype),
        prompt=prompt,
        payload=payload,
        answer_key=key,
        topic_key=f"topic-{uuid.uuid4().hex[:6]}",
    )


@pytest.mark.parametrize(("qtype", "prompt", "payload", "key"), GIVEAWAYS)
def test_a_generated_question_that_shows_its_answer_is_rejected(
    qtype: str, prompt: str, payload: dict[str, Any], key: dict[str, Any]
) -> None:
    with pytest.raises(ValidationError, match="shows its own answer"):
        _generated(qtype, prompt, payload, key)


@pytest.mark.parametrize(("qtype", "prompt", "payload", "key"), FAIR)
def test_a_fair_question_still_parses(
    qtype: str, prompt: str, payload: dict[str, Any], key: dict[str, Any]
) -> None:
    assert _generated(qtype, prompt, payload, key).prompt == prompt


async def test_an_admin_edit_that_puts_the_answer_in_the_prompt_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    question = SimpleNamespace(
        question_type=QuizQuestionType.MULTIPLE_CHOICE,
        prompt="Which store backs the queue?",
        payload=MCQ,
        answer_key={"correct_index": 0},
    )
    repo = SimpleNamespace(get_by_id=AsyncMock(return_value=question))
    monkeypatch.setattr(quiz_review, "QuizQuestionRepository", lambda db, org_id: repo)
    db = AsyncMock()

    with pytest.raises(ValueError, match="shows its own answer"):
        await edit_question(
            db,
            org_id=uuid.uuid4(),
            question_id=uuid.uuid4(),
            edit=QuizReviewEdit(prompt="Redis backs the queue. Which store is it?"),
        )
    db.flush.assert_not_awaited()
