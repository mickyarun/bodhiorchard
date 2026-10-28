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

"""The scheduler's open and reveal passes for one org, at frozen instants.

The org quizzes at 10:00 Kolkata (04:30 UTC) on weekdays with a one-hour
window. Only APPROVED questions may open; drafts, rejects and future-dated
questions stay in the pool.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from app.models.quiz import QuizStatus
from app.models.quiz_question import QuizQuestionStatus as S
from app.schemas.settings import QuizGameSettings
from app.services.quiz_scheduler import _open_pass, _reveal_pass
from tests.fakes.app_state import EventRecorder
from tests.fakes.seed import Factory, seed_org
from tests.integration.gamification_fakes.quiz_fake_support import (
    add_question,
    open_quiz,
    quizzes,
    statuses,
)

pytestmark = pytest.mark.integration

MONDAY_FIRE = datetime(2026, 3, 2, 4, 30, tzinfo=UTC)
CONFIG = {
    "timezone": "Asia/Kolkata",
    "quizTime": "10:00",
    "activeWeekdays": [0, 1, 2, 3, 4],
    "windowMinutes": 60,
    "slackNotifyOpen": False,
}
SETTINGS = QuizGameSettings.model_validate(CONFIG)


async def test_nothing_opens_a_second_early_and_the_oldest_approved_opens_on_time(
    app_sessions: Factory, event_recorder: EventRecorder
) -> None:
    org = await seed_org(app_sessions)
    oldest = await add_question(app_sessions, org.org_id, S.APPROVED)
    newer = await add_question(app_sessions, org.org_id, S.APPROVED)
    draft = await add_question(app_sessions, org.org_id, S.DRAFT)
    rejected = await add_question(app_sessions, org.org_id, S.REJECTED)
    future = await add_question(
        app_sessions, org.org_id, S.APPROVED, scheduled_date=date(2026, 3, 3)
    )

    await _open_pass(org.org_id, SETTINGS, MONDAY_FIRE - timedelta(seconds=1))
    assert await quizzes(app_sessions, org.org_id) == []

    await _open_pass(org.org_id, SETTINGS, MONDAY_FIRE)
    await event_recorder.settle()

    (quiz,) = await quizzes(app_sessions, org.org_id)
    assert (quiz.question_id, quiz.quiz_date, quiz.status) == (
        oldest,
        date(2026, 3, 2),
        QuizStatus.OPEN,
    )
    assert (quiz.open_at, quiz.reveal_at) == (MONDAY_FIRE, MONDAY_FIRE + timedelta(hours=1))
    assert await statuses(app_sessions, oldest, newer, draft, rejected, future) == [
        S.USED,
        S.APPROVED,
        S.DRAFT,
        S.REJECTED,
        S.APPROVED,
    ]
    assert event_recorder.payloads(f"quiz:{org.org_id}") == [{"event_type": "quiz_opened"}]


async def test_a_question_scheduled_for_today_jumps_the_queue(app_sessions: Factory) -> None:
    org = await seed_org(app_sessions)
    await add_question(app_sessions, org.org_id, S.APPROVED)
    today = await add_question(
        app_sessions, org.org_id, S.APPROVED, scheduled_date=date(2026, 3, 2)
    )

    await _open_pass(org.org_id, SETTINGS, MONDAY_FIRE + timedelta(hours=3))

    assert [q.question_id for q in await quizzes(app_sessions, org.org_id)] == [today]


async def test_later_ticks_the_same_day_and_weekend_ticks_open_nothing(
    app_sessions: Factory,
) -> None:
    org = await seed_org(app_sessions)
    for _ in range(3):
        await add_question(app_sessions, org.org_id, S.APPROVED)

    for minutes in (0, 1, 600):
        await _open_pass(org.org_id, SETTINGS, MONDAY_FIRE + timedelta(minutes=minutes))
    await _open_pass(org.org_id, SETTINGS, datetime(2026, 3, 7, 4, 30, tzinfo=UTC))

    assert [q.quiz_date for q in await quizzes(app_sessions, org.org_id)] == [date(2026, 3, 2)]


async def test_an_unreviewed_pool_opens_nothing_and_raises_the_low_queue_signal(
    app_sessions: Factory, event_recorder: EventRecorder
) -> None:
    org = await seed_org(app_sessions)
    draft = await add_question(app_sessions, org.org_id, S.DRAFT)
    rejected = await add_question(app_sessions, org.org_id, S.REJECTED)

    await _open_pass(org.org_id, SETTINGS, MONDAY_FIRE)
    await event_recorder.settle()

    assert await quizzes(app_sessions, org.org_id) == []
    assert await statuses(app_sessions, draft, rejected) == [S.DRAFT, S.REJECTED]
    assert event_recorder.payloads(f"quiz:{org.org_id}") == [
        {"event_type": "low_queue", "approved_remaining": 0}
    ]


async def test_reveal_flips_exactly_at_reveal_time_and_only_once(
    app_sessions: Factory, event_recorder: EventRecorder
) -> None:
    org = await seed_org(app_sessions)
    reveal_at = MONDAY_FIRE + timedelta(hours=1)
    await open_quiz(app_sessions, org.org_id, MONDAY_FIRE, reveal_at)

    await _reveal_pass(org.org_id, SETTINGS, reveal_at - timedelta(seconds=1))
    assert [q.status for q in await quizzes(app_sessions, org.org_id)] == [QuizStatus.OPEN]

    await _reveal_pass(org.org_id, SETTINGS, reveal_at)
    await _reveal_pass(org.org_id, SETTINGS, reveal_at + timedelta(minutes=5))
    await event_recorder.settle()

    assert [q.status for q in await quizzes(app_sessions, org.org_id)] == [QuizStatus.REVEALED]
    assert event_recorder.payloads(f"quiz:{org.org_id}") == [{"event_type": "quiz_revealed"}]
