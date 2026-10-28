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

"""Shared setup for the quiz integration tests: open, answer, close, reveal.

Windows sit hours away from the real clock (the endpoints read ``now``
directly), so no test races a window edge. Closing a quiz moves its reveal time
into the past, which is what the scheduler's reveal pass looks for.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update

from app.models.quiz import Quiz, QuizStatus
from app.models.quiz_answer import QuizAnswer
from app.models.quiz_question import QuizQuestion, QuizQuestionStatus, QuizQuestionType
from app.schemas.settings import QuizGameSettings
from app.services import quiz_notify, quiz_scheduler
from app.services.quiz_content import topic_hash
from tests.integration.leave_support import Factory, as_user

MONTHLY = "/api/v1/quiz/leaderboard"
RIGHT = {"index": 1}
WRONG = {"index": 0}


async def open_quiz(factory: Factory, org: uuid.UUID, *, quiz_date: date) -> uuid.UUID:
    """An open multiple-choice quiz whose right answer is index 1."""
    now = datetime.now(UTC)
    async with factory() as db:
        question = QuizQuestion(
            org_id=org,
            status=QuizQuestionStatus.USED,
            question_type=QuizQuestionType.MULTIPLE_CHOICE,
            prompt="Which planet is hottest?",
            payload={"choices": ["Mercury", "Venus"]},
            answer_key={"correct_index": 1},
            topic_hash=topic_hash(f"planets-{uuid.uuid4()}"),
        )
        db.add(question)
        await db.flush()
        quiz = Quiz(
            org_id=org,
            question_id=question.id,
            quiz_date=quiz_date,
            status=QuizStatus.OPEN,
            open_at=now - timedelta(hours=1),
            reveal_at=now + timedelta(hours=2),
        )
        db.add(quiz)
        await db.commit()
        return quiz.id


async def answer(
    client: AsyncClient,
    org: uuid.UUID,
    user: uuid.UUID,
    quiz_id: uuid.UUID,
    response: dict[str, int],
) -> None:
    """Submit through the real endpoint, which must accept it."""
    sent = await client.post(
        f"/api/v1/quiz/{quiz_id}/answers", json={"response": response}, headers=as_user(user, org)
    )
    assert sent.status_code == 200, sent.text
    assert sent.json()["accepted"] is True


async def close_quiz(factory: Factory, quiz_id: uuid.UUID) -> None:
    """End the answer window, leaving the quiz OPEN for the reveal pass."""
    async with factory() as db:
        await db.execute(
            update(Quiz)
            .where(Quiz.id == quiz_id)
            .values(reveal_at=datetime.now(UTC) - timedelta(minutes=1))
        )
        await db.commit()


async def points_for(factory: Factory, quiz_id: uuid.UUID, user: uuid.UUID) -> int:
    """The points the submit endpoint stored on ``user``'s answer."""
    async with factory() as db:
        row = await db.scalar(
            select(QuizAnswer)
            .where(QuizAnswer.quiz_id == quiz_id)
            .where(QuizAnswer.user_id == user)
        )
        assert row is not None
        return row.points_awarded


def use_test_db(monkeypatch: pytest.MonkeyPatch, factory: Factory) -> None:
    """Point the scheduler and the Slack notifier at the test database."""
    monkeypatch.setattr(quiz_scheduler, "AsyncSessionLocal", factory)
    monkeypatch.setattr(quiz_notify, "AsyncSessionLocal", factory)


def capture_dms(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Collect the quiz Slack messages instead of sending them."""
    sent: list[str] = []

    async def capture(org_id: uuid.UUID, message: str, *, event: str) -> int:
        sent.append(message)
        return 1

    monkeypatch.setattr(quiz_notify, "_dm_all_members", capture)
    return sent


async def reveal_pass(org: uuid.UUID, *, notify_reveal: bool = False) -> None:
    """One scheduler reveal pass for ``org`` (call :func:`use_test_db` first)."""
    settings = QuizGameSettings(slack_notify_reveal=notify_reveal)
    await quiz_scheduler._reveal_pass(org, settings, datetime.now(UTC))


async def monthly_board(
    client: AsyncClient, org: uuid.UUID, viewer: uuid.UUID, *, month: str
) -> list[tuple[str, int, int]]:
    """``(user id, points, correct count)`` rows of the monthly board."""
    board = await client.get(MONTHLY, params={"month": month}, headers=as_user(viewer, org))
    assert board.status_code == 200, board.text
    return [(e["userId"], e["totalPoints"], e["correctCount"]) for e in board.json()]
