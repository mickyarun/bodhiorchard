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

"""A reveal pass that fails on one quiz keeps what it already committed.

Each quiz is revealed and scored in its own transaction. If a later quiz fails,
the earlier ones are still announced, and the failed one is retried next tick.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.quiz import Quiz, QuizStatus
from app.services import quiz_scheduler
from app.services.quiz_reveal import reveal_quiz
from tests.integration.leave_support import Factory, give_role, setup_org
from tests.integration.quiz_support import (
    CORRECT,
    add_quiz,
    answer,
    capture_dms,
    close_quiz,
    monthly_board,
    points_for,
    reveal_pass,
    use_test_db,
)

pytestmark = pytest.mark.integration


async def _status(factory: Factory, quiz_id: uuid.UUID) -> QuizStatus:
    async with factory() as db:
        quiz = await db.get(Quiz, quiz_id)
        assert quiz is not None
        return quiz.status


async def test_a_failed_quiz_does_not_silence_the_ones_already_revealed(
    client: AsyncClient, pg_session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    use_test_db(monkeypatch, pg_session_factory)
    sent = capture_dms(monkeypatch)
    events: list[dict[str, Any]] = []
    monkeypatch.setattr(quiz_scheduler, "publish", lambda topic, payload: events.append(payload))
    org, (ada,), _ = await setup_org(pg_session_factory, "Ada")
    await give_role(pg_session_factory, org, ada, "developer")
    first = await add_quiz(pg_session_factory, org, quiz_date=date(2026, 2, 10))
    second = await add_quiz(pg_session_factory, org, quiz_date=date(2026, 2, 11))
    for quiz_id in (first, second):
        await answer(client, org, ada, quiz_id, CORRECT)
        await close_quiz(pg_session_factory, quiz_id)
    broken = {second}

    async def flaky(
        db: AsyncSession, *, org_id: uuid.UUID, quiz_id: uuid.UUID, quiz_date: date
    ) -> bool:
        won = await reveal_quiz(db, org_id=org_id, quiz_id=quiz_id, quiz_date=quiz_date)
        if quiz_id in broken:
            raise RuntimeError("fold failed")
        return won

    monkeypatch.setattr(quiz_scheduler, "reveal_quiz", flaky)
    await reveal_pass(org, notify_reveal=True)

    first_points = await points_for(pg_session_factory, first, ada)
    assert await _status(pg_session_factory, first) == QuizStatus.REVEALED
    assert await _status(pg_session_factory, second) == QuizStatus.OPEN
    assert events == [{"event_type": "quiz_revealed"}]
    assert len(sent) == 1 and f"Ada — *{first_points}*" in sent[0]
    board = await monthly_board(client, org, ada, month="2026-02")
    assert board == [(str(ada), first_points, 1)]

    broken.clear()
    await reveal_pass(org)
    total = first_points + await points_for(pg_session_factory, second, ada)
    assert await _status(pg_session_factory, second) == QuizStatus.REVEALED
    assert await monthly_board(client, org, ada, month="2026-02") == [(str(ada), total, 2)]
