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

"""Live daily quiz instance — one approved question opened for one org-day.

Created at fire time by the scheduler from an ``APPROVED``
:class:`app.models.quiz_question.QuizQuestion` (which flips to ``USED``). Holds
the absolute open/reveal instants (locked at creation, so a later settings
change never shifts an in-flight quiz) and the per-org-day idempotency key.
Employees' answers FK to this row. The question's type/difficulty are read
through ``question_id`` rather than duplicated here.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class QuizStatus(StrEnum):
    """A live quiz is ``OPEN`` for its window, then flips to ``REVEALED``."""

    OPEN = "open"
    REVEALED = "revealed"


class Quiz(BaseModel):
    """One org's live quiz for one local calendar date."""

    __tablename__ = "quizzes"
    __table_args__ = (
        # Idempotency: the scheduler can never open two quizzes for one org-day.
        UniqueConstraint("org_id", "quiz_date", name="uq_quizzes_org_date"),
        Index("ix_quizzes_org_status", "org_id", "status"),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quiz_questions.id"), nullable=False, index=True
    )
    quiz_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[QuizStatus] = mapped_column(
        Enum(QuizStatus, name="quiz_status", values_callable=lambda e: [x.value for x in e]),
        nullable=False,
        default=QuizStatus.OPEN,
    )
    open_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reveal_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    def __repr__(self) -> str:
        return f"<Quiz(id={self.id}, date={self.quiz_date}, status={self.status})>"
