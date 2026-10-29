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

"""Content a seeded org starts with: registry features and an open quiz.

Both normally come from agent runs (a scan, the quiz writer), which the e2e
stack fakes, so they are written here the way those runs would leave them.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feature import Feature
from app.models.quiz import Quiz, QuizStatus
from app.models.quiz_question import QuizQuestion, QuizQuestionStatus, QuizQuestionType
from tests.e2e_stack.specs import OrgSpec

# Open since an hour ago, revealed hours from now: always live during a run.
_OPENED = timedelta(hours=1)
_REVEALS = timedelta(hours=6)


def add_features(db: AsyncSession, org_id: uuid.UUID, spec: OrgSpec) -> None:
    """Registry features, as a scan's synthesis would have written them."""
    for feature in spec.features:
        db.add(
            Feature(
                org_id=org_id,
                feature_title=feature.title,
                description=feature.description,
                capabilities={"capabilities": []},
                cluster_names=[],
                tags=feature.tags,
                cluster_signature=f"e2e-{uuid.uuid4().hex[:12]}",
            )
        )


async def add_open_quiz(db: AsyncSession, org_id: uuid.UUID, spec: OrgSpec) -> None:
    """Today's quiz, already open, as the scheduler would have opened it."""
    if spec.open_quiz is None:
        return
    question = QuizQuestion(
        org_id=org_id,
        status=QuizQuestionStatus.USED,
        question_type=QuizQuestionType.MULTIPLE_CHOICE,
        prompt=spec.open_quiz.prompt,
        payload={"choices": spec.open_quiz.choices},
        answer_key={"correct_index": spec.open_quiz.correct_index},
        explanation=spec.open_quiz.explanation,
        topic_hash=uuid.uuid4().hex,
    )
    db.add(question)
    await db.flush()
    now = datetime.now(UTC)
    db.add(
        Quiz(
            org_id=org_id,
            question_id=question.id,
            quiz_date=now.date(),
            status=QuizStatus.OPEN,
            open_at=now - _OPENED,
            reveal_at=now + _REVEALS,
        )
    )
