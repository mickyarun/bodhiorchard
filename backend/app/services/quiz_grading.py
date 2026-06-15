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

"""Per-type answer grading — pure registry, mirrors the agent-handler pattern.

``grade(question_type, response, answer_key)`` returns whether the user's
submission is correct. Adding a new ``QuizQuestionType`` is a single registry
entry. Fill-blank matching is normalization-tolerant (case/space/punctuation +
alias list) so a right answer is never marked wrong over trivia.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.models.quiz_question import QuizQuestionType
from app.services.quiz_content import normalize_text


def _grade_multiple_choice(response: dict[str, Any], answer_key: dict[str, Any]) -> bool:
    selected = response.get("index")
    if isinstance(selected, bool) or not isinstance(selected, int):
        return False
    return selected == answer_key.get("correct_index")


def _grade_scramble(response: dict[str, Any], answer_key: dict[str, Any]) -> bool:
    text = response.get("text")
    if not isinstance(text, str):
        return False
    return normalize_text(text) == normalize_text(str(answer_key.get("answer", "")))


def _grade_fill_blank(response: dict[str, Any], answer_key: dict[str, Any]) -> bool:
    text = response.get("text")
    if not isinstance(text, str):
        return False
    submitted = normalize_text(text)
    if not submitted:
        return False
    accepted = {normalize_text(str(answer_key.get("answer", "")))}
    for alias in answer_key.get("aliases", []) or []:
        accepted.add(normalize_text(str(alias)))
    return submitted in accepted


_GRADERS: dict[QuizQuestionType, Callable[[dict[str, Any], dict[str, Any]], bool]] = {
    QuizQuestionType.MULTIPLE_CHOICE: _grade_multiple_choice,
    QuizQuestionType.SCRAMBLE: _grade_scramble,
    QuizQuestionType.FILL_BLANK: _grade_fill_blank,
}


def grade(
    question_type: QuizQuestionType,
    response: dict[str, Any],
    answer_key: dict[str, Any],
) -> bool:
    """Return True if ``response`` correctly answers a question of ``question_type``."""
    grader = _GRADERS.get(question_type)
    if grader is None:  # pragma: no cover — enum is exhaustive
        return False
    return grader(response, answer_key)
