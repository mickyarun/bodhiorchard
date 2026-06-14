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

"""Answer submission orchestration — grade, score, persist (no XP, ever).

Enforces the fairness rules: one attempt per user (idempotent), submissions
only while the window is open, and — critically — the result NEVER reveals
correctness while the quiz is open, so the answer can't be learned by probing.
SQL stays in the repositories; this module only orchestrates them.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.quiz import QuizStatus
from app.repositories.quiz import QuizRepository
from app.repositories.quiz_answer import QuizAnswerRepository
from app.repositories.quiz_score import QuizScoreRepository
from app.services.quiz_constants import score_for_answer
from app.services.quiz_grading import grade


class QuizError(Exception):
    """Base class for quiz submission errors (mapped to HTTP by the API layer)."""


class QuizNotFoundError(QuizError):
    """The quiz does not exist for this org."""


class QuizWindowClosedError(QuizError):
    """The quiz is no longer accepting answers."""


@dataclass(slots=True, frozen=True)
class SubmitResult:
    """Outcome of a submission. Deliberately carries NO correctness while open."""

    accepted: bool
    already_answered: bool


async def submit_answer(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    quiz_id: uuid.UUID,
    response: dict[str, Any],
    speed_grace_minutes: int,
) -> SubmitResult:
    """Record one user's answer to the active quiz.

    Idempotent on re-submit; rejects once the window has closed; updates the
    monthly aggregate (points + streaks) but never touches XP. Returns only
    whether the answer was accepted — correctness is withheld until reveal.
    """
    quiz_repo = QuizRepository(db, org_id=org_id)
    pair = await quiz_repo.get_with_question(quiz_id)
    if pair is None:
        raise QuizNotFoundError("Quiz not found")
    quiz, question = pair

    now = datetime.now(UTC)
    if quiz.status != QuizStatus.OPEN or not (quiz.open_at <= now < quiz.reveal_at):
        raise QuizWindowClosedError("The quiz is not open for answers")

    answer_repo = QuizAnswerRepository(db, org_id=org_id)
    existing = await answer_repo.get(user_id=user_id, question_id=question.id)
    if existing is not None:
        return SubmitResult(accepted=True, already_answered=True)

    is_correct = grade(question.question_type, response, question.answer_key)
    latency_ms = max(0, int((now - quiz.open_at).total_seconds() * 1000))
    points = score_for_answer(
        is_correct=is_correct, latency_ms=latency_ms, grace_minutes=speed_grace_minutes
    )

    _, created = await answer_repo.add(
        quiz_id=quiz.id,
        question_id=question.id,
        user_id=user_id,
        response=response,
        is_correct=is_correct,
        points_awarded=points,
        answered_at=now,
        latency_ms=latency_ms,
    )
    if not created:
        # Lost a race to another in-flight submit — treat as already answered.
        return SubmitResult(accepted=True, already_answered=True)

    prev = await quiz_repo.previous_quiz_with_question(quiz.quiz_date)
    prev_quiz_date = prev[0].quiz_date if prev else None
    score_repo = QuizScoreRepository(db, org_id=org_id)
    await score_repo.record(
        user_id=user_id,
        # Points are attributed to the quiz's own month, not "now" — so an
        # answer submitted just after a month boundary still counts toward the
        # month the quiz opened in. The leaderboard's ?month= selects it.
        period_month=quiz.quiz_date.strftime("%Y-%m"),
        quiz_date=quiz.quiz_date,
        prev_quiz_date=prev_quiz_date,
        is_correct=is_correct,
        points=points,
        latency_ms=latency_ms,
        new_quiz_participation=True,
    )
    return SubmitResult(accepted=True, already_answered=False)
