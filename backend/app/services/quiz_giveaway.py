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
DB, no I/O. Run on every generated draft and on admin edits that touch the
prompt, payload or answer, next to ``validate_question_content``.

Matching is on whole words, so an answer of "Go" is not found inside "going".
In the prompt, which is prose, only a mention written as a name counts (not
all lowercase): "Redis backs the queue" gives "Redis" away, while "lets
players answer one quiz question a day" does not give away a feature called
"Quiz". The short fill-blank hint is checked case-insensitively. Aliases
shorter than three letters or that are common words are ignored, and
true/false or numeric choice sets are never flagged.
"""

from __future__ import annotations

import re
from typing import Any

from app.models.quiz_question import QuizQuestionType
from app.services.quiz_content import normalize_text

_MIN_ALIAS_LENGTH = 3
_STOP_WORDS = frozenset(
    {"and", "are", "for", "from", "not", "one", "our", "the", "this", "that", "with", "you"}
)
_BOOLEAN_WORDS = frozenset({"true", "false", "yes", "no"})


def _occurrences(text: str, phrase: str) -> list[str]:
    """Every whole-word occurrence of ``phrase`` in ``text``, as written there."""
    words = normalize_text(phrase).split()
    if not words:
        return []
    pattern = r"(?<![^\W_])" + r"[\W_]+".join(re.escape(w) for w in words) + r"(?![^\W_])"
    return re.findall(pattern, text, flags=re.IGNORECASE)


def _mentions(text: str, phrase: str) -> bool:
    """``phrase`` appears in ``text`` as whole words, in any case."""
    return bool(_occurrences(text, phrase))


def _names(prose: str, phrase: str) -> bool:
    """``phrase`` appears in ``prose`` written as a name (not all lowercase)."""
    return any(found != found.lower() for found in _occurrences(prose, phrase))


def _letters(value: str) -> str:
    """The folded text with spaces removed, in order."""
    return normalize_text(value).replace(" ", "")


def _is_plain_choice_set(choices: list[str]) -> bool:
    """True/false, yes/no or all-numeric choices: their words occur in any prompt."""
    folded = [normalize_text(c) for c in choices]
    return all(c in _BOOLEAN_WORDS for c in folded) or all(
        c.replace(" ", "").isdigit() for c in folded
    )


def _mcq_giveaway(prompt: str, payload: dict[str, Any], answer_key: dict[str, Any]) -> bool:
    """The prompt names the correct choice and mentions no other choice."""
    choices = [str(c) for c in payload.get("choices") or []]
    index = answer_key.get("correct_index")
    if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < len(choices):
        return False
    if _is_plain_choice_set(choices):
        return False
    others = choices[:index] + choices[index + 1 :]
    return _names(prompt, choices[index]) and not any(_mentions(prompt, c) for c in others)


def _scramble_giveaway(prompt: str, payload: dict[str, Any], answer_key: dict[str, Any]) -> bool:
    """The letters are not actually scrambled, or the prompt names the answer."""
    answer = str(answer_key.get("answer", ""))
    scrambled = str(payload.get("scrambled", ""))
    return _letters(scrambled) == _letters(answer) or _names(prompt, answer)


def _usable_alias(alias: str) -> bool:
    folded = normalize_text(alias)
    return len(folded.replace(" ", "")) >= _MIN_ALIAS_LENGTH and folded not in _STOP_WORDS


def _fill_blank_giveaway(prompt: str, payload: dict[str, Any], answer_key: dict[str, Any]) -> bool:
    """The prompt names, or the hint mentions, the answer or a meaningful alias."""
    accepted = [str(answer_key.get("answer", ""))]
    accepted += [str(a) for a in answer_key.get("aliases", []) or [] if _usable_alias(str(a))]
    hint = str(payload.get("hint", ""))
    return any(_names(prompt, a) or _mentions(hint, a) for a in accepted)


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
