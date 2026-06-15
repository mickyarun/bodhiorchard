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

"""Pure quiz-content helpers — shared by generation, review-edit, and grading.

No DB, no I/O. Three concerns:

* ``validate_question_content`` — assert a ``(type, payload, answer_key)`` triple
  is internally consistent (MCQ index in range, scramble actually scrambles the
  answer, fill-blank has a non-empty answer). Used at generation-persist time
  *and* re-run on every admin edit so a hand-edit can't save a broken question.
* ``normalize_text`` — case/space/punctuation folding for fill-blank matching,
  so a correct answer is never marked wrong over trivia.
* ``topic_hash`` — stable hash of a topic key for non-repetition.
"""

from __future__ import annotations

import hashlib
import re
import string
from typing import Any

from app.models.quiz_question import QuizQuestionType

_WHITESPACE_RE = re.compile(r"\s+")
_PUNCT_TABLE = str.maketrans("", "", string.punctuation)


def normalize_text(value: str) -> str:
    """Fold case, collapse whitespace, and strip punctuation for fair matching."""
    folded = value.strip().lower().translate(_PUNCT_TABLE)
    return _WHITESPACE_RE.sub(" ", folded).strip()


def normalize_topic_key(topic_key: str) -> str:
    """Canonicalize a topic key before hashing (case + whitespace only)."""
    return _WHITESPACE_RE.sub(" ", topic_key.strip().lower())


def topic_hash(topic_key: str) -> str:
    """Stable sha256 of a topic key, used as the non-repetition dedup key."""
    return hashlib.sha256(normalize_topic_key(topic_key).encode("utf-8")).hexdigest()


def _letters_multiset(value: str) -> list[str]:
    """Sorted non-space characters of a string, lowercased — for scramble checks."""
    return sorted(value.lower().replace(" ", ""))


def correct_answer_text(
    question_type: QuizQuestionType,
    payload: dict[str, Any],
    answer_key: dict[str, Any],
) -> str:
    """Human-readable correct answer for display (recap / reveal)."""
    if question_type == QuizQuestionType.MULTIPLE_CHOICE:
        choices = payload.get("choices") or []
        idx = answer_key.get("correct_index")
        if isinstance(idx, int) and not isinstance(idx, bool) and 0 <= idx < len(choices):
            return str(choices[idx])
        return ""
    return str(answer_key.get("answer", ""))


def validate_question_content(
    question_type: QuizQuestionType,
    payload: dict[str, Any],
    answer_key: dict[str, Any],
) -> None:
    """Raise ``ValueError`` if the payload/answer_key are inconsistent for the type.

    Keeps a malformed AI draft — or a bad admin edit — out of the pool, so the
    grader never faces an un-gradeable question at play time.
    """
    if question_type == QuizQuestionType.MULTIPLE_CHOICE:
        choices = payload.get("choices")
        if not isinstance(choices, list) or len(choices) < 2:
            raise ValueError("multiple_choice needs at least two choices")
        if not all(isinstance(c, str) and c.strip() for c in choices):
            raise ValueError("multiple_choice choices must be non-empty strings")
        idx = answer_key.get("correct_index")
        if isinstance(idx, bool) or not isinstance(idx, int) or not 0 <= idx < len(choices):
            raise ValueError("multiple_choice correct_index out of range")

    elif question_type == QuizQuestionType.SCRAMBLE:
        scrambled = payload.get("scrambled")
        answer = answer_key.get("answer")
        if not isinstance(scrambled, str) or not scrambled.strip():
            raise ValueError("scramble needs a non-empty scrambled string")
        if not isinstance(answer, str) or not answer.strip():
            raise ValueError("scramble needs a non-empty answer")
        if _letters_multiset(scrambled) != _letters_multiset(answer):
            raise ValueError("scrambled text is not a rearrangement of the answer")

    elif question_type == QuizQuestionType.FILL_BLANK:
        answer = answer_key.get("answer")
        if not isinstance(answer, str) or not answer.strip():
            raise ValueError("fill_blank needs a non-empty answer")
        aliases = answer_key.get("aliases", [])
        if not isinstance(aliases, list) or not all(isinstance(a, str) for a in aliases):
            raise ValueError("fill_blank aliases must be a list of strings")

    else:  # pragma: no cover — defensive; enum is exhaustive above
        raise ValueError(f"unsupported question_type: {question_type}")
