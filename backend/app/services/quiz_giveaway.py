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

"""Reject a quiz question whose visible parts already reveal its answer.

While a quiz is open players see the prompt and the payload (MCQ choices, the
scrambled letters, the fill-blank hint); only ``answer_key`` is withheld. A
question that repeats its answer in what players see is a giveaway. Pure: no
DB, no I/O. Run on every generated draft and on every admin edit, next to
``validate_question_content``.

Matching is on whole words after ``normalize_text`` folding, so an answer of
"Go" is not found inside "going".
"""

from __future__ import annotations

from typing import Any

from app.models.quiz_question import QuizQuestionType
from app.services.quiz_content import normalize_text


def _shows(text: str, phrase: str) -> bool:
    """True when ``phrase`` appears in ``text`` as whole words (case/punctuation-folded)."""
    needle = normalize_text(phrase)
    return bool(needle) and f" {needle} " in f" {normalize_text(text)} "


def _letters(value: str) -> str:
    """The folded text with spaces removed, in order."""
    return normalize_text(value).replace(" ", "")


def _mcq_giveaway(prompt: str, payload: dict[str, Any], answer_key: dict[str, Any]) -> bool:
    """The prompt names the correct choice and no other choice."""
    choices = [str(c) for c in payload.get("choices") or []]
    index = answer_key.get("correct_index")
    if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < len(choices):
        return False
    others = choices[:index] + choices[index + 1 :]
    return _shows(prompt, choices[index]) and not any(_shows(prompt, c) for c in others)


def _scramble_giveaway(prompt: str, payload: dict[str, Any], answer_key: dict[str, Any]) -> bool:
    """The letters are not actually scrambled, or the prompt names the answer."""
    answer = str(answer_key.get("answer", ""))
    scrambled = str(payload.get("scrambled", ""))
    return _letters(scrambled) == _letters(answer) or _shows(prompt, answer)


def _fill_blank_giveaway(prompt: str, payload: dict[str, Any], answer_key: dict[str, Any]) -> bool:
    """The prompt or the hint contains the answer or one of its aliases."""
    accepted = [str(answer_key.get("answer", ""))]
    accepted += [str(a) for a in answer_key.get("aliases", []) or []]
    hint = str(payload.get("hint", ""))
    return any(_shows(prompt, a) or _shows(hint, a) for a in accepted)


def reject_answer_giveaway(
    question_type: QuizQuestionType,
    prompt: str,
    payload: dict[str, Any],
    answer_key: dict[str, Any],
) -> None:
    """Raise ``ValueError`` when the prompt or payload reveals the answer."""
    checks = {
        QuizQuestionType.MULTIPLE_CHOICE: _mcq_giveaway,
        QuizQuestionType.SCRAMBLE: _scramble_giveaway,
        QuizQuestionType.FILL_BLANK: _fill_blank_giveaway,
    }
    check = checks.get(question_type)
    if check is not None and check(prompt, payload, answer_key):
        raise ValueError(f"{question_type.value} question shows its own answer")
