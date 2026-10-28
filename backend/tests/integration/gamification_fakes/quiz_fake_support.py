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

"""Quiz pool, schedule and score rows for the fake-backed quiz tests."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import select

from app.models.quiz import Quiz, QuizStatus
from app.models.quiz_question import QuizQuestion, QuizQuestionStatus, QuizQuestionType
from app.models.quiz_score import QuizScore
from app.models.user import User
from app.services.quiz_content import topic_hash
from tests.fakes.seed import Factory
from tests.integration.gamification_fakes.sp_support import set_org_config

MCQ_PAYLOAD = {"choices": ["Redis", "Kafka", "Postgres", "SQS"]}


async def enable_quiz(factory: Factory, org_id: uuid.UUID, **quiz: Any) -> None:
    """Store quiz settings (camelCase or snake_case keys) on the org."""
    await set_org_config(factory, org_id, {"quiz": quiz})


async def add_question(
    factory: Factory,
    org_id: uuid.UUID,
    status: QuizQuestionStatus,
    *,
    topic: str | None = None,
    scheduled_date: date | None = None,
    prompt: str = "Which store backs the job queue?",
) -> uuid.UUID:
    """A pooled multiple-choice question in ``status``."""
    async with factory() as db:
        row = QuizQuestion(
            org_id=org_id,
            status=status,
            question_type=QuizQuestionType.MULTIPLE_CHOICE,
            prompt=prompt,
            payload=MCQ_PAYLOAD,
            answer_key={"correct_index": 0},
            topic_hash=topic_hash(topic or uuid.uuid4().hex),
            scheduled_date=scheduled_date,
        )
        db.add(row)
        await db.commit()
        return row.id


async def open_quiz(
    factory: Factory, org_id: uuid.UUID, open_at: datetime, reveal_at: datetime
) -> uuid.UUID:
    """An OPEN quiz on ``open_at``'s date over a fresh USED question."""
    question_id = await add_question(factory, org_id, QuizQuestionStatus.USED)
    async with factory() as db:
        quiz = Quiz(
            org_id=org_id,
            question_id=question_id,
            quiz_date=open_at.date(),
            status=QuizStatus.OPEN,
            open_at=open_at,
            reveal_at=reveal_at,
        )
        db.add(quiz)
        await db.commit()
        return quiz.id


async def statuses(factory: Factory, *question_ids: uuid.UUID) -> list[QuizQuestionStatus]:
    """Current status of each question, in the order given."""
    async with factory() as db:
        found = {
            q.id: q.status
            for q in await db.scalars(
                select(QuizQuestion).where(QuizQuestion.id.in_(question_ids))
            )
        }
    return [found[qid] for qid in question_ids]


async def quizzes(factory: Factory, org_id: uuid.UUID) -> list[Quiz]:
    """Every quiz the org has, oldest date first."""
    async with factory() as db:
        rows = await db.scalars(select(Quiz).where(Quiz.org_id == org_id).order_by(Quiz.quiz_date))
        return list(rows)


async def link_slack(
    factory: Factory, user_id: uuid.UUID, slack_id: str, prefs: dict[str, bool] | None = None
) -> None:
    """Give a member a Slack id and optional notification preferences."""
    async with factory() as db:
        user = await db.get(User, user_id)
        assert user is not None
        user.slack_id = slack_id
        user.notification_prefs = prefs or {}
        await db.commit()


async def deactivate(factory: Factory, user_id: uuid.UUID) -> None:
    """Mark a member inactive (left the company)."""
    async with factory() as db:
        user = await db.get(User, user_id)
        assert user is not None
        user.is_active = False
        await db.commit()


async def seed_score(
    factory: Factory,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    month: str,
    *,
    points: int,
    correct: int,
    time_ms: int = 1000,
) -> None:
    """A member's monthly quiz aggregate."""
    async with factory() as db:
        db.add(
            QuizScore(
                org_id=org_id,
                user_id=user_id,
                period_month=month,
                total_points=points,
                correct_count=correct,
                total_answered=max(correct, 1),
                total_time_ms=time_ms,
                quizzes_played=max(correct, 1),
            )
        )
        await db.commit()
