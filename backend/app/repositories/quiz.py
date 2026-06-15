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

"""Live quiz instance data access — org-scoped.

All SQL touching ``quizzes`` lives here: opening a day's quiz, reading the
active quiz, the conditional reveal flip, and the previous-quiz lookup the
scheduler uses for type rotation and streak continuity.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.quiz import Quiz, QuizStatus
from app.models.quiz_question import QuizQuestion
from app.repositories.base import rowcount


class QuizRepository:
    """Repository scoped by org_id — keeps cross-org queries impossible."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        self._db = db
        self._org_id = org_id

    async def exists_for_date(self, quiz_date: date) -> bool:
        """Cheap open-pass guard — true if a quiz already exists for this org-day."""
        stmt = (
            select(Quiz.id)
            .where(Quiz.org_id == self._org_id)
            .where(Quiz.quiz_date == quiz_date)
            .limit(1)
        )
        return (await self._db.execute(stmt)).scalar_one_or_none() is not None

    async def create(
        self,
        *,
        question_id: uuid.UUID,
        quiz_date: date,
        open_at: datetime,
        reveal_at: datetime,
    ) -> Quiz:
        """Open a quiz for one org-day. The uq(org_id, quiz_date) guards races."""
        row = Quiz(
            org_id=self._org_id,
            question_id=question_id,
            quiz_date=quiz_date,
            status=QuizStatus.OPEN,
            open_at=open_at,
            reveal_at=reveal_at,
        )
        self._db.add(row)
        await self._db.flush()
        return row

    async def get_open_now(self, now: datetime) -> tuple[Quiz, QuizQuestion] | None:
        """The currently-open quiz (status OPEN, ``open_at <= now < reveal_at``), or None.

        Time-based rather than date-based so it's correct regardless of the org's
        timezone and even if the reveal tick hasn't fired yet. The ``open_at``
        bound ensures a future-dated quiz never shows before its window starts.
        """
        stmt = (
            select(Quiz, QuizQuestion)
            .join(QuizQuestion, QuizQuestion.id == Quiz.question_id)
            .where(Quiz.org_id == self._org_id)
            .where(Quiz.status == QuizStatus.OPEN)
            .where(Quiz.open_at <= now)
            .where(Quiz.reveal_at > now)
            .order_by(Quiz.quiz_date.desc())
            .limit(1)
        )
        row = (await self._db.execute(stmt)).first()
        return (row[0], row[1]) if row else None

    async def get_with_question(self, quiz_id: uuid.UUID) -> tuple[Quiz, QuizQuestion] | None:
        """One quiz with its question by id, org-scoped (any status)."""
        stmt = (
            select(Quiz, QuizQuestion)
            .join(QuizQuestion, QuizQuestion.id == Quiz.question_id)
            .where(Quiz.org_id == self._org_id)
            .where(Quiz.id == quiz_id)
        )
        row = (await self._db.execute(stmt)).first()
        return (row[0], row[1]) if row else None

    async def list_open_past_reveal(self, now: datetime) -> list[Quiz]:
        """OPEN quizzes whose window has closed — the reveal pass works this list."""
        stmt = (
            select(Quiz)
            .where(Quiz.org_id == self._org_id)
            .where(Quiz.status == QuizStatus.OPEN)
            .where(Quiz.reveal_at <= now)
        )
        return list((await self._db.execute(stmt)).scalars().all())

    async def flip_to_revealed(self, quiz_id: uuid.UUID) -> bool:
        """Conditionally flip OPEN→REVEALED. Returns True only for the winning
        caller (rowcount==1), so a multi-pod reveal fires Slack exactly once."""
        stmt = (
            update(Quiz)
            .where(Quiz.org_id == self._org_id)
            .where(Quiz.id == quiz_id)
            .where(Quiz.status == QuizStatus.OPEN)
            .values(status=QuizStatus.REVEALED)
        )
        result = await self._db.execute(stmt)
        return (rowcount(result) or 0) == 1

    async def list_closed_in_range(
        self, *, month_start: date, month_end: date, now: datetime
    ) -> list[tuple[Quiz, QuizQuestion]]:
        """Quizzes in ``[month_start, month_end)`` whose window has CLOSED.

        Closed = ``reveal_at <= now`` (time-based, so the recap is correct even
        if the scheduler hasn't yet flipped the status flag). Newest first.
        """
        stmt = (
            select(Quiz, QuizQuestion)
            .join(QuizQuestion, QuizQuestion.id == Quiz.question_id)
            .where(Quiz.org_id == self._org_id)
            .where(Quiz.quiz_date >= month_start)
            .where(Quiz.quiz_date < month_end)
            .where(Quiz.reveal_at <= now)
            .order_by(Quiz.quiz_date.desc())
        )
        return [(r[0], r[1]) for r in (await self._db.execute(stmt)).all()]

    async def previous_quiz_with_question(
        self, before_date: date
    ) -> tuple[Quiz, QuizQuestion] | None:
        """The most recent quiz strictly before ``before_date``, with its question.

        Drives type rotation (exclude the prior type) and streak continuity
        (was the prior quiz the one the user last answered?).
        """
        stmt = (
            select(Quiz, QuizQuestion)
            .join(QuizQuestion, QuizQuestion.id == Quiz.question_id)
            .where(Quiz.org_id == self._org_id)
            .where(Quiz.quiz_date < before_date)
            .order_by(Quiz.quiz_date.desc())
            .limit(1)
        )
        row = (await self._db.execute(stmt)).first()
        return (row[0], row[1]) if row else None
