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

"""The admin approval queue over HTTP: draft -> approved / rejected, and what may open."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient

from app.models.quiz_question import QuizQuestionStatus as S
from app.repositories.quiz_topic_history import QuizTopicHistoryRepository
from app.schemas.settings import QuizGameSettings
from app.services.quiz_content import topic_hash
from app.services.quiz_scheduler import _open_pass
from tests.fakes.seed import Factory, auth_headers, seed_member, seed_org
from tests.integration.gamification_fakes.quiz_fake_support import (
    add_question,
    quizzes,
    statuses,
)

pytestmark = pytest.mark.integration

REVIEW = "/api/v1/quiz/review"
SETTINGS = QuizGameSettings.model_validate(
    {"timezone": "UTC", "quizTime": "10:00", "slackNotifyOpen": False}
)
MONDAY = datetime(2026, 3, 2, 10, 0, tzinfo=UTC)


async def test_approve_and_reject_decide_what_the_scheduler_may_open(
    client: AsyncClient, app_sessions: Factory
) -> None:
    org = await seed_org(app_sessions)
    headers = auth_headers(org.owner_id, org.org_id)
    keep = await add_question(app_sessions, org.org_id, S.DRAFT, topic="keep-topic")
    drop = await add_question(app_sessions, org.org_id, S.DRAFT, topic="drop-topic")

    approved = await client.post(f"{REVIEW}/{keep}/approve", json={}, headers=headers)
    rejected = await client.post(f"{REVIEW}/{drop}/reject", headers=headers)
    listed = await client.get(REVIEW, headers=headers)
    await _open_pass(org.org_id, SETTINGS, MONDAY)

    assert (approved.json()["status"], rejected.json()["status"]) == ("approved", "rejected")
    assert [item["id"] for item in listed.json()] == [str(keep)]
    assert [q.question_id for q in await quizzes(app_sessions, org.org_id)] == [keep]
    async with app_sessions() as db:
        burned = await QuizTopicHistoryRepository(db, org_id=org.org_id).existing_hashes(
            [topic_hash("keep-topic"), topic_hash("drop-topic")]
        )
    assert burned == {topic_hash("keep-topic")}


async def test_an_edit_that_breaks_the_question_is_refused_and_nothing_changes(
    client: AsyncClient, app_sessions: Factory
) -> None:
    org = await seed_org(app_sessions)
    headers = auth_headers(org.owner_id, org.org_id)
    draft = await add_question(app_sessions, org.org_id, S.DRAFT)

    response = await client.patch(
        f"{REVIEW}/{draft}",
        json={"prompt": "Changed?", "answerKey": {"correct_index": 7}},
        headers=headers,
    )
    listed = await client.get(REVIEW, headers=headers)

    assert response.status_code == 422
    assert listed.json()[0]["prompt"] == "Which store backs the job queue?"
    assert listed.json()[0]["answerKey"] == {"correct_index": 0}


async def test_another_orgs_question_is_not_found_and_members_cannot_review(
    client: AsyncClient, app_sessions: Factory
) -> None:
    org = await seed_org(app_sessions)
    other = await seed_org(app_sessions)
    theirs = await add_question(app_sessions, other.org_id, S.DRAFT)
    dev = await seed_member(app_sessions, org.org_id, "dev")
    mine = await add_question(app_sessions, org.org_id, S.DRAFT)

    owner = auth_headers(org.owner_id, org.org_id)
    cross = await client.post(f"{REVIEW}/{theirs}/approve", json={}, headers=owner)
    member = await client.post(
        f"{REVIEW}/{mine}/approve", json={}, headers=auth_headers(dev, org.org_id)
    )
    missing = await client.post(f"{REVIEW}/{uuid.uuid4()}/reject", headers=owner)

    assert (cross.status_code, member.status_code, missing.status_code) == (404, 403, 404)
    assert await statuses(app_sessions, theirs, mine) == [S.DRAFT, S.DRAFT]


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="a played question can be approved again and replayed, "
    "fixed by branch fix/quiz-review-used-question",
)
async def test_a_question_that_already_ran_cannot_be_approved_or_edited_again(
    client: AsyncClient, app_sessions: Factory
) -> None:
    org = await seed_org(app_sessions)
    headers = auth_headers(org.owner_id, org.org_id)
    used = await add_question(app_sessions, org.org_id, S.USED)

    approve = await client.post(f"{REVIEW}/{used}/approve", json={}, headers=headers)
    edit = await client.patch(
        f"{REVIEW}/{used}", json={"answerKey": {"correct_index": 2}}, headers=headers
    )

    assert (approve.status_code, edit.status_code) == (409, 409)
    assert await statuses(app_sessions, used) == [S.USED]


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="an admin edit may make a question print its own answer, "
    "fixed by branch fix/quiz-answer-giveaways",
)
async def test_an_edit_that_puts_the_answer_in_the_prompt_is_refused(
    client: AsyncClient, app_sessions: Factory
) -> None:
    org = await seed_org(app_sessions)
    draft = await add_question(app_sessions, org.org_id, S.DRAFT)
    giveaway = {"prompt": "Redis backs the job queue. Which store backs the job queue?"}

    response = await client.patch(
        f"{REVIEW}/{draft}", json=giveaway, headers=auth_headers(org.owner_id, org.org_id)
    )

    assert response.status_code == 422
