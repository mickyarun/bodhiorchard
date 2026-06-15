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

"""Pydantic schemas for the Company Quiz Game — agent-generation parsing.

These model the strict JSON the generation agent must emit. Content validity
(payload/answer_key consistency per type) is enforced via
``validate_question_content`` so a malformed draft is rejected at parse time.
API request/response DTOs live alongside these as the feature's surface grows.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.models.quiz_question import QuizDifficulty, QuizQuestionStatus, QuizQuestionType
from app.services.quiz_content import validate_question_content


class GeneratedQuestion(BaseModel):
    """One question as emitted by the generation agent (pre-persist)."""

    question_type: QuizQuestionType
    difficulty: QuizDifficulty = QuizDifficulty.MEDIUM
    prompt: str = Field(min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)
    answer_key: dict[str, Any] = Field(default_factory=dict)
    explanation: str = ""
    category: str | None = None
    topic_key: str = Field(min_length=1)
    source_refs: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_content(self) -> GeneratedQuestion:
        """Reject a question whose payload/answer_key don't match its type."""
        validate_question_content(self.question_type, self.payload, self.answer_key)
        return self


class QuizGenerationBatch(BaseModel):
    """Top-level envelope the agent returns: a batch of generated questions."""

    questions: list[GeneratedQuestion] = Field(default_factory=list)


class QuizBatchJobPayload(BaseModel):
    """Async-job payload for one batch-generation run for one org."""

    org_id: str
    count: int = Field(ge=1, le=20)
    difficulty: QuizDifficulty = QuizDifficulty.MEDIUM
    enabled_types: list[QuizQuestionType] = Field(min_length=1)


# ── Player-facing DTOs ─────────────────────────────────────────────


class QuizQuestionPublic(BaseModel):
    """A question as shown WHILE OPEN — the answer/explanation are stripped.

    ``payload`` is always safe to expose: the correct answer lives only in the
    (omitted) ``answer_key``. MCQ choices / the scrambled string / the fill-blank
    hint are the puzzle itself.
    """

    id: uuid.UUID
    question_type: QuizQuestionType = Field(serialization_alias="questionType")
    difficulty: QuizDifficulty
    prompt: str
    payload: dict[str, Any]
    category: str | None = None

    model_config = {"populate_by_name": True}


class QuizActiveRead(BaseModel):
    """Today's open quiz for the current user (answer withheld)."""

    id: uuid.UUID
    quiz_date: date = Field(serialization_alias="quizDate")
    open_at: datetime = Field(serialization_alias="openAt")
    reveal_at: datetime = Field(serialization_alias="revealAt")
    already_answered: bool = Field(serialization_alias="alreadyAnswered")
    question: QuizQuestionPublic

    model_config = {"populate_by_name": True}


class QuizAnswerSubmit(BaseModel):
    """A submission. ``response`` is type-shaped: {"index": n} | {"text": "..."}."""

    response: dict[str, Any]


class QuizAnswerResult(BaseModel):
    """Submit acknowledgement — NEVER carries correctness while the quiz is open."""

    accepted: bool
    already_answered: bool = Field(serialization_alias="alreadyAnswered")

    model_config = {"populate_by_name": True}


class QuizUserAnswer(BaseModel):
    """The caller's own answer, shown at reveal."""

    response: dict[str, Any]
    is_correct: bool = Field(serialization_alias="isCorrect")
    points: int

    model_config = {"populate_by_name": True}


class QuizRevealRead(BaseModel):
    """Post-close payload: full answer, explanation, and social-proof stats."""

    id: uuid.UUID
    question_type: QuizQuestionType = Field(serialization_alias="questionType")
    prompt: str
    payload: dict[str, Any]
    answer_key: dict[str, Any] = Field(serialization_alias="answerKey")
    explanation: str
    category: str | None = None
    source_refs: dict[str, Any] = Field(serialization_alias="sourceRefs")
    total_answers: int = Field(serialization_alias="totalAnswers")
    correct_answers: int = Field(serialization_alias="correctAnswers")
    percent_correct: int = Field(serialization_alias="percentCorrect")
    your_answer: QuizUserAnswer | None = Field(default=None, serialization_alias="yourAnswer")

    model_config = {"populate_by_name": True}


class QuizLeaderboardEntry(BaseModel):
    """One row of the monthly (or all-time) standings."""

    user_id: uuid.UUID = Field(serialization_alias="userId")
    user_name: str = Field(serialization_alias="userName")
    total_points: int = Field(serialization_alias="totalPoints")
    correct_count: int = Field(serialization_alias="correctCount")

    model_config = {"populate_by_name": True}


class QuizDailyEntry(BaseModel):
    """One row of a single quiz's standings (speed + accuracy)."""

    user_id: uuid.UUID = Field(serialization_alias="userId")
    user_name: str = Field(serialization_alias="userName")
    points: int
    is_correct: bool = Field(serialization_alias="isCorrect")
    latency_ms: int = Field(serialization_alias="latencyMs")

    model_config = {"populate_by_name": True}


class QuizRecapItem(BaseModel):
    """One past (window-closed) quiz, with its answer — for the month recap."""

    quiz_date: date = Field(serialization_alias="quizDate")
    question_type: QuizQuestionType = Field(serialization_alias="questionType")
    prompt: str
    correct_answer: str = Field(serialization_alias="correctAnswer")
    explanation: str
    category: str | None = None
    percent_correct: int = Field(serialization_alias="percentCorrect")
    total_answers: int = Field(serialization_alias="totalAnswers")
    you_answered: bool = Field(serialization_alias="youAnswered")
    you_correct: bool | None = Field(default=None, serialization_alias="youCorrect")

    model_config = {"populate_by_name": True}


class QuizRecap(BaseModel):
    """The 'between quizzes' view: this month's answered quizzes + the next one."""

    next_quiz_at: datetime | None = Field(default=None, serialization_alias="nextQuizAt")
    items: list[QuizRecapItem] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


# ── Admin review DTOs ──────────────────────────────────────────────


class QuizReviewItem(BaseModel):
    """A pooled question for the admin review queue (full content + answer)."""

    id: uuid.UUID
    status: QuizQuestionStatus
    question_type: QuizQuestionType = Field(serialization_alias="questionType")
    difficulty: QuizDifficulty
    prompt: str
    payload: dict[str, Any]
    answer_key: dict[str, Any] = Field(serialization_alias="answerKey")
    explanation: str
    category: str | None = None
    source_refs: dict[str, Any] = Field(serialization_alias="sourceRefs")
    scheduled_date: date | None = Field(default=None, serialization_alias="scheduledDate")
    created_at: datetime = Field(serialization_alias="createdAt")

    model_config = {"populate_by_name": True}


class QuizReviewEdit(BaseModel):
    """Admin edit of a pooled question — only provided fields change."""

    prompt: str | None = None
    payload: dict[str, Any] | None = None
    answer_key: dict[str, Any] | None = Field(default=None, alias="answerKey")
    explanation: str | None = None
    difficulty: QuizDifficulty | None = None
    category: str | None = None

    model_config = {"populate_by_name": True}


class QuizApproveRequest(BaseModel):
    """Approve a pooled question, optionally pinning it to a specific date."""

    scheduled_date: date | None = Field(default=None, alias="scheduledDate")

    model_config = {"populate_by_name": True}
