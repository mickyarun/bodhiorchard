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

"""Per-user monthly quiz score aggregate.

Mirrors :class:`app.models.minigame.MinigameScore` but bucketed by calendar
month (``period_month`` = ``"YYYY-MM"``) so the monthly-champion rollup is a
single top-N read. Streaks are quiz-day based (not calendar-day) and carried
forward across month rows by the repository, so a month boundary never breaks a
live streak. ``last_quiz_date`` holds the local date of the last quiz the user
answered, used to decide streak continuity against the org's previous quiz.

Deliberately DECOUPLED from XP — the quiz's only economy effect is one monthly
SP award to the top scorer; nothing here touches ``DeveloperXP`` /
``reward_events``.
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import BigInteger, Date, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class QuizScore(BaseModel):
    """One user's accumulated quiz performance for one calendar month."""

    __tablename__ = "quiz_scores"
    __table_args__ = (
        UniqueConstraint("user_id", "period_month", name="uq_quiz_scores_user_month"),
        Index("ix_quiz_scores_org_month_points", "org_id", "period_month", "total_points"),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    period_month: Mapped[str] = mapped_column(String(7), nullable=False)
    total_points: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    correct_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_answered: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_time_ms: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    quizzes_played: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    participation_streak: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    correct_streak: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    best_streak: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_quiz_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<QuizScore(user={self.user_id}, month={self.period_month}, pts={self.total_points})>"
        )
