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

"""Live quizzes for the quiz integration tests.

Windows are placed hours away from the real clock (the quiz endpoints read
``datetime.now`` directly), so a test never races a window edge.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from app.models.quiz import Quiz, QuizStatus
from app.models.quiz_question import QuizQuestion, QuizQuestionStatus, QuizQuestionType
from app.services.quiz_content import topic_hash
from tests.integration.leave_support import Factory

CHOICES = ["Mercury", "Venus", "Earth"]
CORRECT = {"index": 1}
WRONG = {"index": 2}
EXPLANATION = "Venus is the hottest planet."


async def add_quiz(
    factory: Factory,
    org: uuid.UUID,
    *,
    opened_hours_ago: float = 1,
    closes_in_hours: float = 2,
    status: QuizStatus = QuizStatus.OPEN,
) -> uuid.UUID:
    """One multiple-choice quiz whose answer is index 1; returns the quiz id."""
    now = datetime.now(UTC)
    open_at = now - timedelta(hours=opened_hours_ago)
    async with factory() as db:
        question = QuizQuestion(
            org_id=org,
            status=QuizQuestionStatus.USED,
            question_type=QuizQuestionType.MULTIPLE_CHOICE,
            prompt="Which planet is hottest?",
            payload={"choices": CHOICES},
            answer_key={"correct_index": 1},
            explanation=EXPLANATION,
            topic_hash=topic_hash(f"planets-{uuid.uuid4()}"),
            source_refs={"doc": "secret-source"},
        )
        db.add(question)
        await db.flush()
        quiz = Quiz(
            org_id=org,
            question_id=question.id,
            quiz_date=open_at.date(),
            status=status,
            open_at=open_at,
            reveal_at=now + timedelta(hours=closes_in_hours),
        )
        db.add(quiz)
        await db.commit()
        return quiz.id
