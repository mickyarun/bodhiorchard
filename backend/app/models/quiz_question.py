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

"""Reviewable draft pool of AI-generated quiz questions.

Questions are generated in weekly batches into this pool as ``DRAFT``, then an
admin edits / approves / rejects them. Only an ``APPROVED`` question is ever
promoted to a live :class:`app.models.quiz.Quiz` at fire time, which flips it to
``USED``. The generic ``payload`` / ``answer_key`` JSONB pair keeps the schema
type-agnostic — adding a new :class:`QuizQuestionType` needs no migration:

- multiple-choice → ``payload={"choices": [...]}``, ``answer_key={"correct_index": n}``
- scramble        → ``payload={"scrambled": "...", "kind": "letters"|"order"}``,
                    ``answer_key={"answer": "..."}``
- fill-in-blank   → ``payload={"hint": "..."}``, ``answer_key={"answer": "...", "aliases": [...]}``
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class QuizQuestionStatus(StrEnum):
    """Review lifecycle of a pooled question. Only ``APPROVED`` can go live."""

    DRAFT = "draft"
    APPROVED = "approved"
    REJECTED = "rejected"
    USED = "used"


class QuizQuestionType(StrEnum):
    """Supported question formats. Pluggable — extend here + in the grading registry."""

    MULTIPLE_CHOICE = "multiple_choice"
    SCRAMBLE = "scramble"
    FILL_BLANK = "fill_blank"


class QuizDifficulty(StrEnum):
    """Difficulty rubric. ``MIXED`` is a settings-level choice; a concrete
    question row always stores one of EASY/MEDIUM/HARD."""

    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"
    MIXED = "mixed"


class QuizQuestion(BaseModel):
    """One reviewable, admin-editable quiz question in the draft pool."""

    __tablename__ = "quiz_questions"
    __table_args__ = (Index("ix_quiz_questions_org_status", "org_id", "status"),)

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    status: Mapped[QuizQuestionStatus] = mapped_column(
        Enum(
            QuizQuestionStatus,
            name="quiz_question_status",
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=False,
        default=QuizQuestionStatus.DRAFT,
    )
    question_type: Mapped[QuizQuestionType] = mapped_column(
        Enum(
            QuizQuestionType,
            name="quiz_question_type",
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=False,
    )
    difficulty: Mapped[QuizDifficulty] = mapped_column(
        Enum(
            QuizDifficulty,
            name="quiz_difficulty",
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=False,
        default=QuizDifficulty.MEDIUM,
    )
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    answer_key: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    explanation: Mapped[str] = mapped_column(Text, nullable=False, default="")
    category: Mapped[str | None] = mapped_column(String(80), nullable=True)
    topic_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_refs: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    generation_job_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", name="fk_quiz_questions_approved_by", ondelete="SET NULL"),
        nullable=True,
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    scheduled_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    def __repr__(self) -> str:
        return f"<QuizQuestion(id={self.id}, type={self.question_type}, status={self.status})>"
