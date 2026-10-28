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

"""Answer submission at frozen instants: speed bonus, window edges, month of the points."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.repositories.quiz_score import QuizScoreRepository
from app.services import quiz_scoring
from app.services.quiz_scoring import QuizWindowClosedError, SubmitResult, submit_answer
from tests.fakes.seed import Factory, seed_member, seed_org
from tests.integration.gamification_fakes.ledger_support import xp_event_count
from tests.integration.gamification_fakes.quiz_fake_support import open_quiz
from tests.integration.gamification_fakes.streak_support import FrozenClock, install_clock

pytestmark = pytest.mark.integration

OPEN = datetime(2026, 1, 31, 23, 30, tzinfo=UTC)
REVEAL = OPEN + timedelta(hours=2)
RIGHT = {"index": 0}
WRONG = {"index": 3}


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> type[FrozenClock]:
    """Freeze ``quiz_scoring``'s clock; each test moves it."""
    return install_clock(monkeypatch, quiz_scoring, OPEN)


async def _setup(factory: Factory) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    org = await seed_org(factory)
    player = await seed_member(factory, org.org_id, "player")
    quiz_id = await open_quiz(factory, org.org_id, OPEN, REVEAL)
    return org.org_id, player, quiz_id


async def _submit(
    factory: Factory, org_id: uuid.UUID, user: uuid.UUID, quiz_id: uuid.UUID, response: Any
) -> SubmitResult:
    async with factory() as db:
        result = await submit_answer(
            db,
            org_id=org_id,
            user_id=user,
            quiz_id=quiz_id,
            response=response,
            speed_grace_minutes=60,
        )
        await db.commit()
        return result


async def _points(factory: Factory, org_id: uuid.UUID, user: uuid.UUID, month: str) -> int | None:
    async with factory() as db:
        row = await QuizScoreRepository(db, org_id=org_id).get_for_user_month(
            user_id=user, period_month=month
        )
        return row.total_points if row else None


@pytest.mark.parametrize(
    ("after", "response", "points"),
    [
        (timedelta(0), RIGHT, 150),
        (timedelta(minutes=30), RIGHT, 125),
        (timedelta(minutes=61), RIGHT, 100),
        (timedelta(0), WRONG, 0),
    ],
    ids=["at-open", "half-grace", "after-grace", "wrong-at-open"],
)
async def test_points_are_base_plus_a_decaying_speed_bonus_for_the_quiz_month(
    app_sessions: Factory,
    clock: type[FrozenClock],
    after: timedelta,
    response: dict[str, int],
    points: int,
) -> None:
    org_id, player, quiz_id = await _setup(app_sessions)
    clock.set_local(OPEN + after)

    result = await _submit(app_sessions, org_id, player, quiz_id, response)

    assert result == SubmitResult(accepted=True, already_answered=False)
    assert await _points(app_sessions, org_id, player, "2026-01") == points
    assert await _points(app_sessions, org_id, player, "2026-02") is None
    assert await xp_event_count(app_sessions, org_id) == 0


@pytest.mark.parametrize(
    "moment", [OPEN - timedelta(microseconds=1), REVEAL], ids=["before-open", "at-reveal"]
)
async def test_answers_outside_the_window_are_refused_and_not_recorded(
    app_sessions: Factory, clock: type[FrozenClock], moment: datetime
) -> None:
    org_id, player, quiz_id = await _setup(app_sessions)
    clock.set_local(moment)

    with pytest.raises(QuizWindowClosedError):
        await _submit(app_sessions, org_id, player, quiz_id, RIGHT)

    assert await _points(app_sessions, org_id, player, "2026-01") is None


async def test_a_second_answer_is_acknowledged_but_never_rescored(
    app_sessions: Factory, clock: type[FrozenClock]
) -> None:
    org_id, player, quiz_id = await _setup(app_sessions)
    clock.set_local(OPEN + timedelta(minutes=90))
    await _submit(app_sessions, org_id, player, quiz_id, WRONG)

    clock.set_local(OPEN + timedelta(minutes=91))
    again = await _submit(app_sessions, org_id, player, quiz_id, RIGHT)

    assert again == SubmitResult(accepted=True, already_answered=True)
    assert await _points(app_sessions, org_id, player, "2026-01") == 0
