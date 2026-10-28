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

"""The daily top-up keeps each org's review pool at one question per quiz day plus two."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.models.quiz_question import QuizQuestionStatus as S
from app.schemas.settings import QuizGameSettings
from app.services.job_queue import JOB_QUIZ_BATCH
from app.services.quiz_batch_generation import _topup_org
from app.services.quiz_scheduler import _open_pass
from tests.fakes.seed import Factory, seed_org
from tests.integration.gamification_fakes.quiz_batch_support import CreatedJob, JobRecorder
from tests.integration.gamification_fakes.quiz_fake_support import add_question, enable_quiz

pytestmark = pytest.mark.integration

WEEKDAYS = {"activeWeekdays": [0, 1, 2, 3, 4], "difficulty": "hard", "slackNotifyOpen": False}


@pytest.fixture
def jobs(monkeypatch: pytest.MonkeyPatch) -> JobRecorder:
    """Capture the generation jobs the top-up enqueues."""
    recorder = JobRecorder()
    recorder.install(monkeypatch)
    return recorder


async def test_an_empty_pool_asks_for_a_full_week_plus_the_buffer(
    app_sessions: Factory, jobs: JobRecorder
) -> None:
    org = await seed_org(app_sessions)
    await enable_quiz(app_sessions, org.org_id, **WEEKDAYS, enabledQuestionTypes=["scramble"])

    assert await _topup_org(org.org_id) == 7

    assert jobs.created == [
        CreatedJob(
            JOB_QUIZ_BATCH,
            {
                "org_id": str(org.org_id),
                "count": 7,
                "difficulty": "hard",
                "enabled_types": ["scramble"],
            },
        )
    ]


async def test_only_drafts_and_approved_count_toward_the_target(
    app_sessions: Factory, jobs: JobRecorder
) -> None:
    org = await seed_org(app_sessions)
    await enable_quiz(app_sessions, org.org_id, **WEEKDAYS)
    for status, count in [(S.DRAFT, 3), (S.APPROVED, 2), (S.REJECTED, 4), (S.USED, 4)]:
        for _ in range(count):
            await add_question(app_sessions, org.org_id, status)

    assert await _topup_org(org.org_id) == 2
    assert [job.payload["count"] for job in jobs.created] == [2]


@pytest.mark.parametrize(
    ("config", "stock"),
    [({**WEEKDAYS}, 7), ({**WEEKDAYS, "enabled": False}, 0), ({"activeWeekdays": [2]}, 3)],
    ids=["stocked", "disabled", "one-day-a-week-stocked"],
)
async def test_a_stocked_or_disabled_org_enqueues_nothing(
    app_sessions: Factory, jobs: JobRecorder, config: dict[str, object], stock: int
) -> None:
    org = await seed_org(app_sessions)
    await enable_quiz(app_sessions, org.org_id, **config)
    for _ in range(stock):
        await add_question(app_sessions, org.org_id, S.APPROVED)

    assert await _topup_org(org.org_id) == 0
    assert jobs.created == []


async def test_after_a_quiz_runs_the_next_top_up_replaces_the_question_it_used(
    app_sessions: Factory, jobs: JobRecorder
) -> None:
    org = await seed_org(app_sessions)
    await enable_quiz(app_sessions, org.org_id, **WEEKDAYS)
    for _ in range(7):
        await add_question(app_sessions, org.org_id, S.APPROVED)
    assert await _topup_org(org.org_id) == 0

    settings = QuizGameSettings.model_validate({**WEEKDAYS, "timezone": "UTC"})
    await _open_pass(org.org_id, settings, datetime(2026, 3, 2, 10, 0, tzinfo=UTC))

    assert await _topup_org(org.org_id) == 1
    assert [job.payload["count"] for job in jobs.created] == [1]
