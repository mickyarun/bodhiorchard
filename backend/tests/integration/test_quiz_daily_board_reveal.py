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

"""The per-quiz board shows correctness, so it stays shut until reveal time.

Windows sit hours away from the real clock (the endpoints read ``now``
directly), so no test races a window edge.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient

from app.models.quiz import Quiz, QuizStatus
from app.models.quiz_answer import QuizAnswer
from app.models.quiz_question import QuizQuestion, QuizQuestionStatus, QuizQuestionType
from app.services.quiz_content import topic_hash
from tests.integration.leave_support import Factory, as_user, give_role, setup_org

pytestmark = pytest.mark.integration
DAILY = "/api/v1/quiz/leaderboard/daily"


async def _answered_quiz(
    factory: Factory, org: uuid.UUID, user: uuid.UUID, *, closes_in_hours: float
) -> uuid.UUID:
    """A multiple-choice quiz that ``user`` answered correctly."""
    now = datetime.now(UTC)
    open_at = now - timedelta(hours=30 if closes_in_hours < 0 else 1)
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
            quiz_date=open_at.date(),
            status=QuizStatus.OPEN,
            open_at=open_at,
            reveal_at=now + timedelta(hours=closes_in_hours),
        )
        db.add(quiz)
        await db.flush()
        db.add(
            QuizAnswer(
                org_id=org,
                quiz_id=quiz.id,
                question_id=question.id,
                user_id=user,
                response={"index": 1},
                is_correct=True,
                points_awarded=10,
                answered_at=open_at + timedelta(minutes=1),
                latency_ms=60_000,
            )
        )
        await db.commit()
        return quiz.id


async def test_the_daily_board_is_refused_while_the_quiz_is_open(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """Neither the player who answered nor a colleague learns who was right."""
    org, (dev, peer), _ = await setup_org(pg_session_factory, "Dev", "Peer")
    for user in (dev, peer):
        await give_role(pg_session_factory, org, user, "developer")
    quiz_id = await _answered_quiz(pg_session_factory, org, dev, closes_in_hours=2)
    for viewer in (dev, peer):
        response = await client.get(
            DAILY, params={"quiz_id": str(quiz_id)}, headers=as_user(viewer, org)
        )
        assert response.status_code == 403
        assert response.json()["detail"] == "The quiz has not been revealed yet"


async def test_the_daily_board_opens_after_reveal_and_only_for_this_org(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """After the window it ranks answers; another org's quiz id is a 404."""
    org, (dev,), _ = await setup_org(pg_session_factory, "Dev")
    other, (outsider,), _ = await setup_org(pg_session_factory, "Outsider")
    await give_role(pg_session_factory, org, dev, "developer")
    await give_role(pg_session_factory, other, outsider, "developer")
    quiz_id = await _answered_quiz(pg_session_factory, org, dev, closes_in_hours=-6)
    board = await client.get(DAILY, params={"quiz_id": str(quiz_id)}, headers=as_user(dev, org))
    assert board.status_code == 200
    assert [(e["userId"], e["isCorrect"], e["points"]) for e in board.json()] == [
        (str(dev), True, 10)
    ]
    foreign = await client.get(
        DAILY, params={"quiz_id": str(quiz_id)}, headers=as_user(outsider, other)
    )
    assert foreign.status_code == 404
