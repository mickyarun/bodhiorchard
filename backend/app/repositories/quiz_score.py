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

"""Monthly quiz-score aggregate data access — org-scoped.

Mirrors ``MinigameRepository`` (FOR UPDATE + SAVEPOINT upsert). Streaks are
quiz-day based and carried forward across month rows: a fresh month seeds its
streak fields from the user's most recent prior row, so a month boundary never
breaks a live streak.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.quiz_score import QuizScore
from app.models.user import User


@dataclass(slots=True, frozen=True)
class ScoreOutcome:
    """Result of recording one answer into the monthly aggregate."""

    total_points: int
    participation_streak: int
    correct_streak: int
    best_streak: int


@dataclass(slots=True, frozen=True)
class StreakAdvance:
    """The three streak values after advancing for one quiz participation."""

    participation_streak: int
    correct_streak: int
    best_streak: int


def compute_streak_advance(
    *,
    prev_participation: int,
    prev_correct: int,
    prev_best: int,
    last_quiz_date: date | None,
    prev_quiz_date: date | None,
    is_correct: bool,
) -> StreakAdvance:
    """Pure quiz-day streak math (extracted so it's testable without a DB).

    Continuity holds when the user's last-answered quiz is the org's
    immediately-preceding quiz. Participation grows on continuity else resets to
    1; the correct streak grows only while answers stay correct and contiguous,
    and resets to 0 on a wrong answer.
    """
    continuity = last_quiz_date is not None and last_quiz_date == prev_quiz_date
    participation = prev_participation + 1 if continuity else 1
    if not is_correct:
        correct = 0
    elif continuity:
        correct = prev_correct + 1
    else:
        correct = 1
    return StreakAdvance(
        participation_streak=participation,
        correct_streak=correct,
        best_streak=max(prev_best, participation),
    )


@dataclass(slots=True, frozen=True)
class MonthlyLeaderboardRow:
    user_id: uuid.UUID
    user_name: str
    total_points: int
    correct_count: int
    total_time_ms: int


class QuizScoreRepository:
    """Repository scoped by org_id — keeps cross-org queries impossible."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        self._db = db
        self._org_id = org_id

    async def record(
        self,
        *,
        user_id: uuid.UUID,
        period_month: str,
        quiz_date: date,
        prev_quiz_date: date | None,
        is_correct: bool,
        points: int,
        latency_ms: int,
        new_quiz_participation: bool,
    ) -> ScoreOutcome:
        """Fold one answer into the user's monthly aggregate.

        ``new_quiz_participation`` is True the first time the user answers within
        a given quiz; only then do streaks advance and ``quizzes_played``
        increment (so a future multi-question quiz can't inflate them).
        Continuity for streaks holds when the user's previously-answered quiz is
        the org's immediately-preceding quiz (``last_quiz_date == prev_quiz_date``).
        """
        row = await self._get_or_create(user_id, period_month)

        row.total_points += points
        row.total_answered += 1
        row.total_time_ms += latency_ms
        if is_correct:
            row.correct_count += 1

        if new_quiz_participation:
            row.quizzes_played += 1
            advance = compute_streak_advance(
                prev_participation=row.participation_streak,
                prev_correct=row.correct_streak,
                prev_best=row.best_streak,
                last_quiz_date=row.last_quiz_date,
                prev_quiz_date=prev_quiz_date,
                is_correct=is_correct,
            )
            row.participation_streak = advance.participation_streak
            row.correct_streak = advance.correct_streak
            row.best_streak = advance.best_streak
            row.last_quiz_date = quiz_date

        await self._db.flush()
        return ScoreOutcome(
            total_points=row.total_points,
            participation_streak=row.participation_streak,
            correct_streak=row.correct_streak,
            best_streak=row.best_streak,
        )

    async def leaderboard(self, *, period_month: str, limit: int) -> list[MonthlyLeaderboardRow]:
        """Monthly ranking: points desc, then more-correct, then fastest cumulative."""
        stmt = (
            select(
                QuizScore.user_id,
                User.name,
                QuizScore.total_points,
                QuizScore.correct_count,
                QuizScore.total_time_ms,
            )
            .join(User, User.id == QuizScore.user_id)
            .where(QuizScore.org_id == self._org_id)
            .where(QuizScore.period_month == period_month)
            .where(QuizScore.total_answered > 0)
            .order_by(
                QuizScore.total_points.desc(),
                QuizScore.correct_count.desc(),
                QuizScore.total_time_ms.asc(),
                User.name.asc(),
            )
            .limit(limit)
        )
        result = await self._db.execute(stmt)
        return [
            MonthlyLeaderboardRow(
                user_id=r.user_id,
                user_name=r.name or "",
                total_points=r.total_points,
                correct_count=r.correct_count,
                total_time_ms=r.total_time_ms,
            )
            for r in result.all()
        ]

    async def get_for_user_month(
        self, *, user_id: uuid.UUID, period_month: str
    ) -> QuizScore | None:
        """Read one user's row for a month (for the dashboard card), or None."""
        stmt = (
            select(QuizScore)
            .where(QuizScore.org_id == self._org_id)
            .where(QuizScore.user_id == user_id)
            .where(QuizScore.period_month == period_month)
        )
        return (await self._db.execute(stmt)).scalar_one_or_none()

    async def _latest_for_user(self, user_id: uuid.UUID) -> QuizScore | None:
        """The user's most recent monthly row, used to carry streaks forward."""
        stmt = (
            select(QuizScore)
            .where(QuizScore.org_id == self._org_id)
            .where(QuizScore.user_id == user_id)
            .order_by(QuizScore.period_month.desc())
            .limit(1)
        )
        return (await self._db.execute(stmt)).scalar_one_or_none()

    async def _get_or_create(self, user_id: uuid.UUID, period_month: str) -> QuizScore:
        stmt = (
            select(QuizScore)
            .where(QuizScore.org_id == self._org_id)
            .where(QuizScore.user_id == user_id)
            .where(QuizScore.period_month == period_month)
            .with_for_update()
        )
        existing = (await self._db.execute(stmt)).scalar_one_or_none()
        if existing is not None:
            return existing

        # Seed streaks from the user's most recent prior month so a month
        # boundary doesn't reset a live streak.
        prior = await self._latest_for_user(user_id)
        row = QuizScore(
            org_id=self._org_id,
            user_id=user_id,
            period_month=period_month,
            participation_streak=prior.participation_streak if prior else 0,
            correct_streak=prior.correct_streak if prior else 0,
            best_streak=prior.best_streak if prior else 0,
            last_quiz_date=prior.last_quiz_date if prior else None,
        )
        try:
            async with self._db.begin_nested():
                self._db.add(row)
            return row
        except IntegrityError:
            existing = (await self._db.execute(stmt)).scalar_one_or_none()
            if existing is None:
                raise
            return existing
