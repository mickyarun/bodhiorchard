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

"""Quiz question (draft pool) data access — org-scoped.

All SQL touching ``quiz_questions`` lives here: drafting generated questions,
the admin review queue, approval/rejection, the denylist feeds for batch
generation, and the scheduler's atomic "claim the next approved question".
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.quiz_question import (
    QuizDifficulty,
    QuizQuestion,
    QuizQuestionStatus,
    QuizQuestionType,
)


class QuizQuestionRepository:
    """Repository scoped by org_id — keeps cross-org queries impossible."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        self._db = db
        self._org_id = org_id

    async def add_draft(
        self,
        *,
        question_type: QuizQuestionType,
        difficulty: QuizDifficulty,
        prompt: str,
        payload: dict[str, Any],
        answer_key: dict[str, Any],
        explanation: str,
        category: str | None,
        topic_hash: str,
        source_refs: dict[str, Any],
        generation_job_id: str | None,
    ) -> QuizQuestion:
        """Insert one generated question into the pool as DRAFT."""
        row = QuizQuestion(
            org_id=self._org_id,
            status=QuizQuestionStatus.DRAFT,
            question_type=question_type,
            difficulty=difficulty,
            prompt=prompt,
            payload=payload,
            answer_key=answer_key,
            explanation=explanation,
            category=category,
            topic_hash=topic_hash,
            source_refs=source_refs,
            generation_job_id=generation_job_id,
        )
        self._db.add(row)
        await self._db.flush()
        return row

    async def get_by_id(self, question_id: uuid.UUID) -> QuizQuestion | None:
        """Fetch one pooled question by id, org-scoped."""
        stmt = (
            select(QuizQuestion)
            .where(QuizQuestion.org_id == self._org_id)
            .where(QuizQuestion.id == question_id)
        )
        return (await self._db.execute(stmt)).scalar_one_or_none()

    async def list_by_status(
        self, *, statuses: list[QuizQuestionStatus], limit: int = 100
    ) -> list[QuizQuestion]:
        """Review-queue read: pooled questions in the given statuses, newest first."""
        stmt = (
            select(QuizQuestion)
            .where(QuizQuestion.org_id == self._org_id)
            .where(QuizQuestion.status.in_(statuses))
            .order_by(QuizQuestion.created_at.desc())
            .limit(limit)
        )
        return list((await self._db.execute(stmt)).scalars().all())

    async def count_by_status(self, status: QuizQuestionStatus) -> int:
        """Count pooled questions in one status (drives the low-queue nudge)."""
        stmt = (
            select(func.count(QuizQuestion.id))
            .where(QuizQuestion.org_id == self._org_id)
            .where(QuizQuestion.status == status)
        )
        return (await self._db.execute(stmt)).scalar() or 0

    async def pending_topic_hashes(self) -> set[str]:
        """topic_hashes of DRAFT/APPROVED questions — dedupe a new batch against the queue."""
        stmt = (
            select(QuizQuestion.topic_hash)
            .where(QuizQuestion.org_id == self._org_id)
            .where(
                QuizQuestion.status.in_([QuizQuestionStatus.DRAFT, QuizQuestionStatus.APPROVED])
            )
        )
        return set((await self._db.execute(stmt)).scalars().all())

    async def pending_topic_labels(self, limit: int = 100) -> list[str]:
        """Human-readable topics of pooled questions, for the agent denylist."""
        stmt = (
            select(QuizQuestion.prompt)
            .where(QuizQuestion.org_id == self._org_id)
            .where(
                QuizQuestion.status.in_([QuizQuestionStatus.DRAFT, QuizQuestionStatus.APPROVED])
            )
            .order_by(QuizQuestion.created_at.desc())
            .limit(limit)
        )
        return list((await self._db.execute(stmt)).scalars().all())

    async def set_status(
        self,
        question: QuizQuestion,
        *,
        status: QuizQuestionStatus,
        approved_by_user_id: uuid.UUID | None = None,
        approved_at: datetime | None = None,
        scheduled_date: date | None = None,
    ) -> QuizQuestion:
        """Transition a pooled question (approve / reject), recording the actor."""
        question.status = status
        if approved_by_user_id is not None:
            question.approved_by_user_id = approved_by_user_id
        if approved_at is not None:
            question.approved_at = approved_at
        if scheduled_date is not None:
            question.scheduled_date = scheduled_date
        await self._db.flush()
        return question

    async def claim_next_approved(
        self, *, today: date, exclude_type: QuizQuestionType | None
    ) -> QuizQuestion | None:
        """Atomically take the next eligible APPROVED question and mark it USED.

        Eligibility: approved, and either unscheduled or scheduled for today or
        earlier. Preference order: a question explicitly scheduled for today,
        then a type that differs from ``exclude_type`` (no-immediate-repeat
        rotation — a preference, not a filter, so a single remaining type still
        runs), then oldest-approved first. ``FOR UPDATE SKIP LOCKED`` keeps two
        schedulers from claiming the same row.
        """
        order_by: list[Any] = [case((QuizQuestion.scheduled_date == today, 0), else_=1)]
        if exclude_type is not None:
            order_by.append(case((QuizQuestion.question_type != exclude_type, 0), else_=1))
        order_by.append(QuizQuestion.created_at.asc())

        stmt = (
            select(QuizQuestion)
            .where(QuizQuestion.org_id == self._org_id)
            .where(QuizQuestion.status == QuizQuestionStatus.APPROVED)
            .where(
                or_(
                    QuizQuestion.scheduled_date.is_(None),
                    QuizQuestion.scheduled_date <= today,
                )
            )
            .order_by(*order_by)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        row = (await self._db.execute(stmt)).scalar_one_or_none()
        if row is None:
            return None
        row.status = QuizQuestionStatus.USED
        await self._db.flush()
        return row
