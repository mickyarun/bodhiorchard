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

"""Company Quiz Game — admin review/approval API (gated by org:edit_settings).

Split out from ``quiz.py`` (player endpoints) to keep each module focused and
under the file-size bar. Mounted under the same ``/api/v1/quiz`` prefix.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db, require_permissions
from app.models.quiz_question import QuizQuestion, QuizQuestionStatus
from app.models.user import User
from app.repositories.organization import OrganizationRepository
from app.schemas.quiz import (
    QuizApproveRequest,
    QuizBatchJobPayload,
    QuizReviewEdit,
    QuizReviewItem,
)
from app.services.job_queue import JOB_QUIZ_BATCH, create_job
from app.services.org_settings import get_quiz_settings
from app.services.quiz_review import (
    QuizQuestionNotFoundError,
    approve_question,
    edit_question,
    list_review_queue,
    reject_question,
)

router = APIRouter(tags=["quiz"])

_EDIT = Depends(require_permissions("org:edit_settings"))


def _review_item(question: QuizQuestion) -> QuizReviewItem:
    return QuizReviewItem(
        id=question.id,
        status=question.status,
        question_type=question.question_type,
        difficulty=question.difficulty,
        prompt=question.prompt,
        payload=question.payload,
        answer_key=question.answer_key,
        explanation=question.explanation,
        category=question.category,
        source_refs=question.source_refs,
        scheduled_date=question.scheduled_date,
        created_at=question.created_at,
    )


@router.get("/review", response_model=list[QuizReviewItem], dependencies=[_EDIT])
async def list_review(
    status_filter: QuizQuestionStatus | None = Query(default=None, alias="status"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[QuizReviewItem]:
    """List the review queue. Defaults to DRAFT + APPROVED when no status given."""
    statuses = (
        [status_filter]
        if status_filter is not None
        else [QuizQuestionStatus.DRAFT, QuizQuestionStatus.APPROVED]
    )
    rows = await list_review_queue(db, org_id=current_user.org_id, statuses=statuses)
    return [_review_item(q) for q in rows]


@router.patch("/review/{question_id}", response_model=QuizReviewItem, dependencies=[_EDIT])
async def edit_review_question(
    question_id: uuid.UUID,
    body: QuizReviewEdit,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> QuizReviewItem:
    """Edit a pooled question; content is re-validated before saving."""
    try:
        question = await edit_question(
            db, org_id=current_user.org_id, question_id=question_id, edit=body
        )
    except QuizQuestionNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Question not found") from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    await db.commit()
    return _review_item(question)


@router.post("/review/{question_id}/approve", response_model=QuizReviewItem, dependencies=[_EDIT])
async def approve_review_question(
    question_id: uuid.UUID,
    body: QuizApproveRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> QuizReviewItem:
    """Approve a pooled question so it becomes eligible to go live."""
    try:
        question = await approve_question(
            db,
            org_id=current_user.org_id,
            question_id=question_id,
            approver_id=current_user.id,
            scheduled_date=body.scheduled_date,
        )
    except QuizQuestionNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Question not found") from exc
    await db.commit()
    return _review_item(question)


@router.post("/review/{question_id}/reject", response_model=QuizReviewItem, dependencies=[_EDIT])
async def reject_review_question(
    question_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> QuizReviewItem:
    """Reject a pooled question; it never goes live and its topic isn't burned."""
    try:
        question = await reject_question(db, org_id=current_user.org_id, question_id=question_id)
    except QuizQuestionNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Question not found") from exc
    await db.commit()
    return _review_item(question)


@router.post("/review/regenerate", status_code=status.HTTP_202_ACCEPTED, dependencies=[_EDIT])
async def regenerate_one(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Enqueue a single-question draft batch on demand."""
    org_id = current_user.org_id
    settings = get_quiz_settings(await OrganizationRepository(db).get_config(org_id))
    job = create_job(
        JOB_QUIZ_BATCH,
        payload=QuizBatchJobPayload(
            org_id=str(org_id),
            count=1,
            difficulty=settings.difficulty,
            enabled_types=settings.enabled_question_types,
        ).model_dump(mode="json"),
        user_id=str(current_user.id),
    )
    return {"jobId": job.job_id}
