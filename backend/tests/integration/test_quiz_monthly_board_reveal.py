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

"""The monthly board moves at reveal, never when someone answers.

If an answer's points reached the monthly totals at submit time, anyone
watching the board while the quiz is open would see who just answered
correctly. Points are folded in by the reveal pass instead, exactly once.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient

from app.models.quiz_score import QuizScore
from app.repositories.quiz_answer import QuizAnswerRepository
from tests.integration.leave_support import Factory, give_role, setup_org
from tests.integration.quiz_support import (
    RIGHT,
    WRONG,
    answer,
    close_quiz,
    monthly_board,
    open_quiz,
    points_for,
    reveal_pass,
    use_test_db,
)

pytestmark = pytest.mark.integration


async def test_a_right_answer_stays_off_the_monthly_board_until_reveal(
    client: AsyncClient, pg_session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """While the quiz is open the board doesn't move; after reveal it shows the points."""
    use_test_db(monkeypatch, pg_session_factory)
    org, (dev, peer), _ = await setup_org(pg_session_factory, "Dev", "Peer")
    for user in (dev, peer):
        await give_role(pg_session_factory, org, user, "developer")
    today = datetime.now(UTC).date()
    month = today.strftime("%Y-%m")
    quiz_id = await open_quiz(pg_session_factory, org, quiz_date=today)

    await answer(client, org, dev, quiz_id, RIGHT)
    await answer(client, org, peer, quiz_id, WRONG)
    assert await monthly_board(client, org, peer, month=month) == []

    await close_quiz(pg_session_factory, quiz_id)
    await reveal_pass(org)
    points = await points_for(pg_session_factory, quiz_id, dev)
    assert points > 0
    assert await monthly_board(client, org, peer, month=month) == [
        (str(dev), points, 1),
        (str(peer), 0, 0),
    ]


async def test_repeated_and_concurrent_reveal_passes_count_each_answer_once(
    client: AsyncClient, pg_session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two passes racing, then a third, still leave one quiz's worth of points."""
    use_test_db(monkeypatch, pg_session_factory)
    org, (dev,), _ = await setup_org(pg_session_factory, "Dev")
    await give_role(pg_session_factory, org, dev, "developer")
    today = datetime.now(UTC).date()
    quiz_id = await open_quiz(pg_session_factory, org, quiz_date=today)
    await answer(client, org, dev, quiz_id, RIGHT)
    await close_quiz(pg_session_factory, quiz_id)

    await asyncio.gather(reveal_pass(org), reveal_pass(org))
    await reveal_pass(org)

    points = await points_for(pg_session_factory, quiz_id, dev)
    board = await monthly_board(client, org, dev, month=today.strftime("%Y-%m"))
    assert board == [(str(dev), points, 1)]
    async with pg_session_factory() as db:
        repo = QuizAnswerRepository(db, org_id=org)
        assert await repo.claim_unscored(quiz_id=quiz_id, scored_at=datetime.now(UTC)) == []
        await db.rollback()


async def test_scores_already_counted_at_submit_are_not_counted_again(
    client: AsyncClient, pg_session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An answer scored at submit before the reveal fold existed keeps its single count.

    The migration marks every such answer scored. This sets up that state for a
    quiz still open: the old answer and its monthly row, plus a new answer
    submitted under the new rule, then reveals the quiz.
    """
    use_test_db(monkeypatch, pg_session_factory)
    org, (old, new), _ = await setup_org(pg_session_factory, "Old", "New")
    for user in (old, new):
        await give_role(pg_session_factory, org, user, "developer")
    today = datetime.now(UTC).date()
    month = today.strftime("%Y-%m")
    quiz_id = await open_quiz(pg_session_factory, org, quiz_date=today)
    await answer(client, org, old, quiz_id, RIGHT)
    old_points = await points_for(pg_session_factory, quiz_id, old)
    async with pg_session_factory() as db:
        repo = QuizAnswerRepository(db, org_id=org)
        await repo.claim_unscored(quiz_id=quiz_id, scored_at=datetime.now(UTC))
        db.add(
            QuizScore(
                org_id=org,
                user_id=old,
                period_month=month,
                total_points=old_points,
                correct_count=1,
                total_answered=1,
                quizzes_played=1,
                participation_streak=1,
                correct_streak=1,
                best_streak=1,
                last_quiz_date=today,
            )
        )
        await db.commit()
    await answer(client, org, new, quiz_id, RIGHT)

    await close_quiz(pg_session_factory, quiz_id)
    await reveal_pass(org)

    new_points = await points_for(pg_session_factory, quiz_id, new)
    board = dict((u, (p, c)) for u, p, c in await monthly_board(client, org, old, month=month))
    assert board == {str(old): (old_points, 1), str(new): (new_points, 1)}
