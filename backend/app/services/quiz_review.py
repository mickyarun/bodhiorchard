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

"""Admin review/approval orchestration for the quiz draft pool.

Edits are re-validated against the per-type content rules so a hand-edit can
never save an un-gradeable question. Approval records the topic in history so
future generation batches avoid repeating it. SQL stays in the repositories.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.quiz_question import QuizQuestion, QuizQuestionStatus
from app.repositories.quiz_question import QuizQuestionRepository
from app.repositories.quiz_topic_history import QuizTopicHistoryRepository
from app.schemas.quiz import QuizReviewEdit
from app.services.quiz_content import validate_question_content

_TOPIC_LABEL_MAX = 255


class QuizQuestionNotFoundError(Exception):
    """The pooled question does not exist for this org."""


async def list_review_queue(
    db: AsyncSession, *, org_id: uuid.UUID, statuses: list[QuizQuestionStatus], limit: int = 100
) -> list[QuizQuestion]:
    """Return pooled questions in the given statuses for the review UI."""
    repo = QuizQuestionRepository(db, org_id=org_id)
    return await repo.list_by_status(statuses=statuses, limit=limit)


async def _require(repo: QuizQuestionRepository, question_id: uuid.UUID) -> QuizQuestion:
    question = await repo.get_by_id(question_id)
    if question is None:
        raise QuizQuestionNotFoundError("Question not found")
    return question


async def edit_question(
    db: AsyncSession, *, org_id: uuid.UUID, question_id: uuid.UUID, edit: QuizReviewEdit
) -> QuizQuestion:
    """Apply an admin edit, re-validating content. Raises ValueError if invalid."""
    repo = QuizQuestionRepository(db, org_id=org_id)
    question = await _require(repo, question_id)

    if edit.prompt is not None:
        question.prompt = edit.prompt
    if edit.payload is not None:
        question.payload = edit.payload
    if edit.answer_key is not None:
        question.answer_key = edit.answer_key
    if edit.explanation is not None:
        question.explanation = edit.explanation
    if edit.difficulty is not None:
        question.difficulty = edit.difficulty
    if edit.category is not None:
        question.category = edit.category

    # Re-run the per-type content check so a bad hand-edit can't be saved.
    validate_question_content(question.question_type, question.payload, question.answer_key)
    await db.flush()
    return question


async def approve_question(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    question_id: uuid.UUID,
    approver_id: uuid.UUID,
    scheduled_date: Any = None,
) -> QuizQuestion:
    """Approve a question and record its topic so future batches avoid it."""
    repo = QuizQuestionRepository(db, org_id=org_id)
    question = await _require(repo, question_id)

    await repo.set_status(
        question,
        status=QuizQuestionStatus.APPROVED,
        approved_by_user_id=approver_id,
        approved_at=datetime.now(UTC),
        scheduled_date=scheduled_date,
    )
    history = QuizTopicHistoryRepository(db, org_id=org_id)
    await history.upsert(
        topic_hash=question.topic_hash,
        topic_label=question.prompt[:_TOPIC_LABEL_MAX],
        used_date=datetime.now(UTC).date(),
    )
    return question


async def reject_question(
    db: AsyncSession, *, org_id: uuid.UUID, question_id: uuid.UUID
) -> QuizQuestion:
    """Reject a pooled question (it never goes live; its topic isn't burned)."""
    repo = QuizQuestionRepository(db, org_id=org_id)
    question = await _require(repo, question_id)
    return await repo.set_status(question, status=QuizQuestionStatus.REJECTED)
