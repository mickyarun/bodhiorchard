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

"""Company Quiz Game HTTP API — player endpoints + admin review.

Handlers are thin: validate, delegate to services/repositories, shape the
response. The active-quiz endpoint NEVER includes the answer; correctness is
exposed only by ``/reveal`` after the window closes.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.user import User
from app.repositories.organization import OrganizationRepository
from app.repositories.quiz import QuizRepository
from app.repositories.quiz_answer import QuizAnswerRepository
from app.repositories.quiz_score import QuizScoreRepository
from app.schemas.quiz import (
    QuizActiveRead,
    QuizAnswerResult,
    QuizAnswerSubmit,
    QuizDailyEntry,
    QuizLeaderboardEntry,
    QuizQuestionPublic,
    QuizRecap,
    QuizRecapItem,
    QuizRevealRead,
    QuizUserAnswer,
)
from app.services.org_settings import get_quiz_settings
from app.services.quiz_content import correct_answer_text
from app.services.quiz_schedule_math import (
    current_month_key,
    month_bounds,
    next_quiz_at,
    resolve_zone,
)
from app.services.quiz_scoring import (
    QuizNotFoundError,
    QuizWindowClosedError,
    submit_answer,
)

router = APIRouter(tags=["quiz"])


def _public_question(question) -> QuizQuestionPublic:  # type: ignore[no-untyped-def]
    return QuizQuestionPublic(
        id=question.id,
        question_type=question.question_type,
        difficulty=question.difficulty,
        prompt=question.prompt,
        payload=question.payload,
        category=question.category,
    )


@router.get("/active", response_model=QuizActiveRead | None)
async def get_active_quiz(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> QuizActiveRead | None:
    """Return the currently-open quiz (answer withheld), or null if none."""
    org_id = current_user.org_id
    pair = await QuizRepository(db, org_id=org_id).get_open_now(datetime.now(UTC))
    if pair is None:
        return None
    quiz, question = pair
    answered = (
        await QuizAnswerRepository(db, org_id=org_id).get(
            user_id=current_user.id, question_id=question.id
        )
        is not None
    )
    return QuizActiveRead(
        id=quiz.id,
        quiz_date=quiz.quiz_date,
        open_at=quiz.open_at,
        reveal_at=quiz.reveal_at,
        already_answered=answered,
        question=_public_question(question),
    )


@router.post("/{quiz_id}/answers", response_model=QuizAnswerResult)
async def submit_quiz_answer(
    quiz_id: uuid.UUID,
    body: QuizAnswerSubmit,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> QuizAnswerResult:
    """Submit an answer. Returns only acceptance — never correctness while open."""
    org_id = current_user.org_id
    config = await OrganizationRepository(db).get_config(org_id)
    grace = get_quiz_settings(config).speed_grace_minutes
    try:
        result = await submit_answer(
            db,
            org_id=org_id,
            user_id=current_user.id,
            quiz_id=quiz_id,
            response=body.response,
            speed_grace_minutes=grace,
        )
    except QuizNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Quiz not found") from exc
    except QuizWindowClosedError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "The quiz window has closed") from exc
    await db.commit()
    return QuizAnswerResult(accepted=result.accepted, already_answered=result.already_answered)


@router.get("/{quiz_id}/reveal", response_model=QuizRevealRead)
async def get_quiz_reveal(
    quiz_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> QuizRevealRead:
    """Return the answer, explanation, and stats — only once the quiz is revealed."""
    org_id = current_user.org_id
    pair = await QuizRepository(db, org_id=org_id).get_with_question(quiz_id)
    if pair is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Quiz not found")
    quiz, question = pair
    # Reveal is safe once the window has CLOSED (time-based) — independent of the
    # status flag, which the scheduler flips only for one-shot Slack/event firing.
    if datetime.now(UTC) < quiz.reveal_at:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "The quiz has not been revealed yet")

    answer_repo = QuizAnswerRepository(db, org_id=org_id)
    stats = await answer_repo.stats_for_question(question.id)
    mine = await answer_repo.get(user_id=current_user.id, question_id=question.id)
    your_answer = (
        QuizUserAnswer(
            response=mine.response, is_correct=mine.is_correct, points=mine.points_awarded
        )
        if mine
        else None
    )
    percent = round(stats.correct / stats.total * 100) if stats.total else 0
    return QuizRevealRead(
        id=quiz.id,
        question_type=question.question_type,
        prompt=question.prompt,
        payload=question.payload,
        answer_key=question.answer_key,
        explanation=question.explanation,
        category=question.category,
        source_refs=question.source_refs,
        total_answers=stats.total,
        correct_answers=stats.correct,
        percent_correct=percent,
        your_answer=your_answer,
    )


@router.get("/leaderboard", response_model=list[QuizLeaderboardEntry])
async def get_monthly_leaderboard(
    month: str | None = Query(default=None, description="YYYY-MM; defaults to current month"),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[QuizLeaderboardEntry]:
    """Top scorers for a month (defaults to the current month)."""
    period = month or current_month_key(datetime.now(UTC).date())
    rows = await QuizScoreRepository(db, org_id=current_user.org_id).leaderboard(
        period_month=period, limit=limit
    )
    return [
        QuizLeaderboardEntry(
            user_id=r.user_id,
            user_name=r.user_name,
            total_points=r.total_points,
            correct_count=r.correct_count,
        )
        for r in rows
    ]


@router.get("/leaderboard/daily", response_model=list[QuizDailyEntry])
async def get_daily_leaderboard(
    quiz_id: uuid.UUID = Query(...),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[QuizDailyEntry]:
    """Per-quiz ranking by points then speed."""
    rows = await QuizAnswerRepository(db, org_id=current_user.org_id).daily_leaderboard(
        quiz_id=quiz_id, limit=limit
    )
    return [
        QuizDailyEntry(
            user_id=r.user_id,
            user_name=r.user_name,
            points=r.points,
            is_correct=r.is_correct,
            latency_ms=r.latency_ms,
        )
        for r in rows
    ]


@router.get("/recap", response_model=QuizRecap)
async def get_recap(
    month: str | None = Query(default=None, description="YYYY-MM; defaults to current month"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> QuizRecap:
    """The 'between quizzes' view: this month's closed quizzes (with answers) +
    when the next quiz opens. Powers the quiz hub's no-open-quiz state."""
    org_id = current_user.org_id
    now = datetime.now(UTC)
    period = month or current_month_key(now.date())
    month_start, month_end = month_bounds(period)

    quiz_repo = QuizRepository(db, org_id=org_id)
    answer_repo = QuizAnswerRepository(db, org_id=org_id)
    closed = await quiz_repo.list_closed_in_range(
        month_start=month_start, month_end=month_end, now=now
    )

    items: list[QuizRecapItem] = []
    for quiz, question in closed:
        stats = await answer_repo.stats_for_question(question.id)
        mine = await answer_repo.get(user_id=current_user.id, question_id=question.id)
        items.append(
            QuizRecapItem(
                quiz_date=quiz.quiz_date,
                question_type=question.question_type,
                prompt=question.prompt,
                correct_answer=correct_answer_text(
                    question.question_type, question.payload, question.answer_key
                ),
                explanation=question.explanation,
                category=question.category,
                percent_correct=(round(stats.correct / stats.total * 100) if stats.total else 0),
                total_answers=stats.total,
                you_answered=mine is not None,
                you_correct=mine.is_correct if mine else None,
            )
        )

    settings = get_quiz_settings(await OrganizationRepository(db).get_config(org_id))
    upcoming = (
        next_quiz_at(
            now_utc=now,
            zone=resolve_zone(settings.timezone),
            quiz_time=settings.quiz_time,
            active_weekdays=settings.active_weekdays,
        )
        if settings.enabled
        else None
    )
    return QuizRecap(next_quiz_at=upcoming, items=items)
