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

"""The review routes answer 409 for a question that already ran as a quiz."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.models.quiz_question import QuizQuestion, QuizQuestionStatus, QuizQuestionType
from tests.integration.leave_support import Factory, as_user, give_role, setup_org

pytestmark = pytest.mark.integration

REVIEW = "/api/v1/quiz/review"


async def _question(factory: Factory, org: uuid.UUID, status: QuizQuestionStatus) -> uuid.UUID:
    async with factory() as db:
        row = QuizQuestion(
            org_id=org,
            status=status,
            question_type=QuizQuestionType.MULTIPLE_CHOICE,
            prompt="Which store backs the job queue?",
            payload={"choices": ["Redis", "Kafka"]},
            answer_key={"correct_index": 0},
            topic_hash=uuid.uuid4().hex,
        )
        db.add(row)
        await db.commit()
        return row.id


async def _status(factory: Factory, question_id: uuid.UUID) -> QuizQuestionStatus:
    async with factory() as db:
        row = await db.get(QuizQuestion, question_id)
        assert row is not None
        return row.status


async def test_reject_approve_and_edit_of_a_used_question_answer_409(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, (master,), _ = await setup_org(pg_session_factory, "Master")
    await give_role(pg_session_factory, org, master, "quiz_master")
    headers = as_user(master, org)
    used = await _question(pg_session_factory, org, QuizQuestionStatus.USED)
    draft = await _question(pg_session_factory, org, QuizQuestionStatus.DRAFT)

    reject = await client.post(f"{REVIEW}/{used}/reject", headers=headers)
    approve = await client.post(f"{REVIEW}/{used}/approve", json={}, headers=headers)
    edit = await client.patch(f"{REVIEW}/{used}", json={"prompt": "New?"}, headers=headers)
    fresh = await client.post(f"{REVIEW}/{draft}/reject", headers=headers)

    assert (reject.status_code, approve.status_code, edit.status_code) == (409, 409, 409)
    assert fresh.status_code == 200
    assert await _status(pg_session_factory, used) == QuizQuestionStatus.USED
