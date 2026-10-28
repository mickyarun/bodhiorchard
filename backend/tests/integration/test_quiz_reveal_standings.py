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

"""Everything that reads the monthly totals sees a quiz's points once it is revealed.

The reveal DM's standings are read after the fold commits, and the monthly SP
award waits until every quiz of the month has been revealed.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.developer_xp import DeveloperXP
from app.services import quiz_monthly_rollup, quiz_notify
from tests.integration.leave_support import Factory, give_role, setup_org
from tests.integration.quiz_support import (
    RIGHT,
    WRONG,
    answer,
    close_quiz,
    open_quiz,
    points_for,
    reveal_pass,
    use_test_db,
)

pytestmark = pytest.mark.integration


async def test_the_reveal_dm_ranks_the_points_just_revealed(
    client: AsyncClient, pg_session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The reveal message lists the player who answered right, with this quiz's points."""
    use_test_db(monkeypatch, pg_session_factory)
    sent: list[str] = []

    async def capture(org_id: uuid.UUID, message: str, *, event: str) -> int:
        sent.append(message)
        return 1

    monkeypatch.setattr(quiz_notify, "_dm_all_members", capture)
    org, (ada, bob), _ = await setup_org(pg_session_factory, "Ada", "Bob")
    for user in (ada, bob):
        await give_role(pg_session_factory, org, user, "developer")
    quiz_id = await open_quiz(pg_session_factory, org, quiz_date=datetime.now(UTC).date())
    await answer(client, org, ada, quiz_id, RIGHT)
    await answer(client, org, bob, quiz_id, WRONG)

    await close_quiz(pg_session_factory, quiz_id)
    await reveal_pass(org, notify_reveal=True)

    points = await points_for(pg_session_factory, quiz_id, ada)
    assert len(sent) == 1
    assert "This month's leaders:" in sent[0]
    assert f"Ada — *{points}*" in sent[0]
    assert "Bob" not in sent[0]


async def _skill_points(factory: Factory, org: uuid.UUID, user: uuid.UUID) -> float:
    async with factory() as db:
        row = await db.scalar(
            select(DeveloperXP).where(DeveloperXP.org_id == org, DeveloperXP.user_id == user)
        )
        return float(row.skill_points) if row else 0.0


async def test_the_monthly_prize_waits_for_the_last_reveal_of_the_month(
    client: AsyncClient, pg_session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A month with a quiz still open isn't settled; once it's revealed the true leader wins.

    Both players got the first quiz right. Only Ada gets the second one right,
    but until it is revealed the totals can't know that, so settling early
    would split or misplace the prize.
    """
    use_test_db(monkeypatch, pg_session_factory)
    monkeypatch.setattr(quiz_monthly_rollup, "AsyncSessionLocal", pg_session_factory)
    settle = quiz_monthly_rollup.finalize_org_month
    org, (ada, bob), _ = await setup_org(pg_session_factory, "Ada", "Bob")
    for user in (ada, bob):
        await give_role(pg_session_factory, org, user, "developer")
    first = await open_quiz(pg_session_factory, org, quiz_date=date(2026, 1, 29))
    second = await open_quiz(pg_session_factory, org, quiz_date=date(2026, 1, 30))
    await answer(client, org, ada, first, RIGHT)
    await answer(client, org, bob, first, RIGHT)
    await close_quiz(pg_session_factory, first)
    await reveal_pass(org)
    await answer(client, org, ada, second, RIGHT)
    await answer(client, org, bob, second, WRONG)

    assert await settle(org, period_month="2026-01", amount=1.0) == 0

    await close_quiz(pg_session_factory, second)
    await reveal_pass(org)
    assert await settle(org, period_month="2026-01", amount=1.0) == 1
    assert await _skill_points(pg_session_factory, org, ada) > 0
    assert await _skill_points(pg_session_factory, org, bob) == 0
