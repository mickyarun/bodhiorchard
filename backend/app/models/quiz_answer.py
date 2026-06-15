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

"""One employee's single answer to one quiz question.

Unique on ``(user_id, question_id)`` so each person answers a question exactly
once; a re-submit is an idempotent no-op. The ``response`` JSONB is type-shaped
(MCQ: ``{"index": n}``; scramble: ``{"order": [...]}``/``{"text": "..."}``;
fill-blank: ``{"text": "..."}``) so one table serves every question type.
``latency_ms`` is snapshotted from ``answered_at - quiz.open_at`` at submit time
to drive the speed bonus without recomputation.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class QuizAnswer(BaseModel):
    """A single, idempotent submission by one user for one question."""

    __tablename__ = "quiz_answers"
    __table_args__ = (
        UniqueConstraint("user_id", "question_id", name="uq_quiz_answers_user_question"),
        Index("ix_quiz_answers_quiz_user", "quiz_id", "user_id"),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    quiz_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quizzes.id"), nullable=False, index=True
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quiz_questions.id"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    response: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    points_awarded: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    answered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    def __repr__(self) -> str:
        return (
            f"<QuizAnswer(user={self.user_id}, q={self.question_id}, correct={self.is_correct})>"
        )
