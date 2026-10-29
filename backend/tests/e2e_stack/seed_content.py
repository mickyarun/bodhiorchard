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

"""Content added to a seeded org: registry features and an open quiz.

Both normally come from agent runs (a scan, the quiz writer), which the e2e
stack fakes. The quiz goes through the same repository steps the writer
and the scheduler take (draft, approve, claim, open). Features are rows:
scans write them through an agent tool, with no service to call instead.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feature import Feature
from app.models.quiz_question import QuizDifficulty, QuizQuestionStatus, QuizQuestionType
from app.repositories.organization import OrganizationRepository
from app.repositories.quiz import QuizRepository
from app.repositories.quiz_question import QuizQuestionRepository
from tests.e2e_stack.specs import FeaturesSpec, QuizSpec

# Open since an hour ago, revealed hours from now: always live during a run.
_OPENED = timedelta(hours=1)
_REVEALS = timedelta(hours=6)


async def _require_org(db: AsyncSession, org_id: uuid.UUID) -> None:
    if await OrganizationRepository(db).get_by_id(org_id) is None:
        raise HTTPException(status_code=404, detail="no such org")


async def add_features(db: AsyncSession, org_id: uuid.UUID, spec: FeaturesSpec) -> None:
    """Registry features, as a scan's synthesis would have written them."""
    await _require_org(db, org_id)
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
    await db.commit()


async def open_quiz(db: AsyncSession, org_id: uuid.UUID, spec: QuizSpec) -> None:
    """Today's quiz, already open. The org must have been seeded with ``quiz``."""
    await _require_org(db, org_id)
    if spec.correct_index >= len(spec.choices):
        raise HTTPException(status_code=400, detail="correct_index is past the last choice")
    questions = QuizQuestionRepository(db, org_id=org_id)
    draft = await questions.add_draft(
        question_type=QuizQuestionType.MULTIPLE_CHOICE,
        difficulty=QuizDifficulty.EASY,
        prompt=spec.prompt,
        payload={"choices": spec.choices},
        answer_key={"correct_index": spec.correct_index},
        explanation=spec.explanation,
        category=None,
        topic_hash=uuid.uuid4().hex,
        source_refs={},
        generation_job_id=None,
    )
    now = datetime.now(UTC)
    await questions.set_status(draft, status=QuizQuestionStatus.APPROVED, approved_at=now)
    claimed = await questions.claim_next_approved(today=now.date(), exclude_type=None)
    if claimed is None or claimed.id != draft.id:
        raise HTTPException(status_code=409, detail="the org already has approved questions")
    await QuizRepository(db, org_id=org_id).create(
        question_id=claimed.id,
        quiz_date=now.date(),
        open_at=now - _OPENED,
        reveal_at=now + _REVEALS,
    )
    await db.commit()
