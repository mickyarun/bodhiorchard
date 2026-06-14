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

"""Quiz answer data access — org-scoped, idempotent submissions + stats."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.quiz_answer import QuizAnswer
from app.models.user import User


@dataclass(slots=True, frozen=True)
class QuestionStats:
    """Reveal-screen aggregate: how many got it right out of how many answered."""

    total: int
    correct: int


@dataclass(slots=True, frozen=True)
class DailyLeaderboardRow:
    user_id: uuid.UUID
    user_name: str
    points: int
    is_correct: bool
    latency_ms: int


class QuizAnswerRepository:
    """Repository scoped by org_id — keeps cross-org queries impossible."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        self._db = db
        self._org_id = org_id

    async def get(self, *, user_id: uuid.UUID, question_id: uuid.UUID) -> QuizAnswer | None:
        """The user's existing answer to a question, or None."""
        stmt = (
            select(QuizAnswer)
            .where(QuizAnswer.org_id == self._org_id)
            .where(QuizAnswer.user_id == user_id)
            .where(QuizAnswer.question_id == question_id)
        )
        return (await self._db.execute(stmt)).scalar_one_or_none()

    async def add(
        self,
        *,
        quiz_id: uuid.UUID,
        question_id: uuid.UUID,
        user_id: uuid.UUID,
        response: dict[str, Any],
        is_correct: bool,
        points_awarded: int,
        answered_at: datetime,
        latency_ms: int,
    ) -> tuple[QuizAnswer, bool]:
        """Insert one answer. Returns (row, created); created=False on re-submit.

        The uq(user_id, question_id) constraint enforces one attempt; a racing
        second submit hits it and we return the persisted row instead.
        """
        existing = await self.get(user_id=user_id, question_id=question_id)
        if existing is not None:
            return existing, False

        row = QuizAnswer(
            org_id=self._org_id,
            quiz_id=quiz_id,
            question_id=question_id,
            user_id=user_id,
            response=response,
            is_correct=is_correct,
            points_awarded=points_awarded,
            answered_at=answered_at,
            latency_ms=latency_ms,
        )
        try:
            async with self._db.begin_nested():
                self._db.add(row)
            return row, True
        except IntegrityError:
            existing = await self.get(user_id=user_id, question_id=question_id)
            if existing is None:
                raise
            return existing, False

    async def list_for_user_quiz(
        self, *, user_id: uuid.UUID, quiz_id: uuid.UUID
    ) -> list[QuizAnswer]:
        """The user's answers within one quiz (v1 has one, but kept general)."""
        stmt = (
            select(QuizAnswer)
            .where(QuizAnswer.org_id == self._org_id)
            .where(QuizAnswer.quiz_id == quiz_id)
            .where(QuizAnswer.user_id == user_id)
        )
        return list((await self._db.execute(stmt)).scalars().all())

    async def stats_for_question(self, question_id: uuid.UUID) -> QuestionStats:
        """Total answers and correct count for the reveal %-got-it-right figure."""
        stmt = (
            select(
                func.count(QuizAnswer.id),
                func.count(QuizAnswer.id).filter(QuizAnswer.is_correct.is_(True)),
            )
            .where(QuizAnswer.org_id == self._org_id)
            .where(QuizAnswer.question_id == question_id)
        )
        total, correct = (await self._db.execute(stmt)).one()
        return QuestionStats(total=total or 0, correct=correct or 0)

    async def daily_leaderboard(
        self, *, quiz_id: uuid.UUID, limit: int
    ) -> list[DailyLeaderboardRow]:
        """Per-quiz ranking: points desc, then fastest correct, then name."""
        stmt = (
            select(
                QuizAnswer.user_id,
                User.name,
                QuizAnswer.points_awarded,
                QuizAnswer.is_correct,
                QuizAnswer.latency_ms,
            )
            .join(User, User.id == QuizAnswer.user_id)
            .where(QuizAnswer.org_id == self._org_id)
            .where(QuizAnswer.quiz_id == quiz_id)
            .order_by(
                QuizAnswer.points_awarded.desc(),
                QuizAnswer.latency_ms.asc(),
                User.name.asc(),
            )
            .limit(limit)
        )
        result = await self._db.execute(stmt)
        return [
            DailyLeaderboardRow(
                user_id=r.user_id,
                user_name=r.name or "",
                points=r.points_awarded,
                is_correct=r.is_correct,
                latency_ms=r.latency_ms,
            )
            for r in result.all()
        ]
