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

"""One full scheduler tick over several orgs, with the clock frozen at fire time."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

import pytest

from app.models.quiz_question import QuizQuestionStatus
from app.repositories.organization import OrganizationRepository
from app.repositories.quiz import QuizRepository
from app.services import quiz_scheduler
from app.services.quiz_scheduler import tick_once
from tests.fakes.seed import Factory, seed_org
from tests.integration.gamification_fakes.frozen_clock import install_clock
from tests.integration.gamification_fakes.log_tap import LogTap
from tests.integration.gamification_fakes.quiz_fake_support import (
    add_question,
    enable_quiz,
    quizzes,
)

pytestmark = pytest.mark.integration

FIRE = datetime(2026, 3, 2, 10, 0, tzinfo=UTC)
QUIZ = {"timezone": "UTC", "quizTime": "10:00", "slackNotifyOpen": False}


async def _org(factory: Factory, **quiz: object) -> uuid.UUID:
    org = await seed_org(factory)
    await enable_quiz(factory, org.org_id, **quiz)
    await add_question(factory, org.org_id, QuizQuestionStatus.APPROVED)
    return org.org_id


async def test_a_tick_opens_enabled_orgs_skips_disabled_ones_and_survives_a_broken_one(
    app_sessions: Factory, monkeypatch: pytest.MonkeyPatch, failure_log_tap: LogTap
) -> None:
    broken = await _org(app_sessions, **QUIZ)
    enabled = await _org(app_sessions, **QUIZ)
    disabled = await _org(app_sessions, **QUIZ, enabled=False)

    async def only_these(_: OrganizationRepository) -> list[uuid.UUID]:
        return [broken, enabled, disabled]

    real_exists = QuizRepository.exists_for_date

    async def exists_or_fail(self: QuizRepository, quiz_date: date) -> bool:
        if self._org_id == broken:
            raise RuntimeError("database went away for this org")
        return await real_exists(self, quiz_date)

    monkeypatch.setattr(OrganizationRepository, "list_all_ids", only_these)
    monkeypatch.setattr(QuizRepository, "exists_for_date", exists_or_fail)
    install_clock(monkeypatch, quiz_scheduler, FIRE)
    failure_log_tap.allow("quiz_scheduler_org_failed")

    await tick_once()

    assert [q.quiz_date for q in await quizzes(app_sessions, enabled)] == [date(2026, 3, 2)]
    assert await quizzes(app_sessions, disabled) == []
    assert await quizzes(app_sessions, broken) == []
    assert failure_log_tap.failures == ["quiz_scheduler_org_failed"]
