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

"""The daily quiz over HTTP: the answer stays hidden until the window closes."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.quiz_answer import QuizAnswer
from tests.integration.gamification_support import make_org, org_reward_count
from tests.integration.leave_support import Factory, as_user, give_role
from tests.integration.quiz_support import (
    CHOICES,
    CORRECT,
    EXPLANATION,
    WRONG,
    add_quiz,
    close_quiz,
    reveal_pass,
    use_test_db,
)

pytestmark = pytest.mark.integration
QUIZ = "/api/v1/quiz"


async def test_the_open_quiz_shows_the_puzzle_and_nothing_that_answers_it(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """No answer key, explanation or source references while the quiz is open."""
    org, (dev,) = await make_org(pg_session_factory, "Dev")
    quiz_id = await add_quiz(pg_session_factory, org)
    response = await client.get(f"{QUIZ}/active", headers=as_user(dev, org))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == str(quiz_id) and body["alreadyAnswered"] is False
    assert body["question"]["payload"] == {"choices": CHOICES}
    for leak in ("correct_index", "answer_key", "answerKey", "secret-source", EXPLANATION):
        assert leak not in response.text


async def test_submitting_says_accepted_and_never_whether_it_was_right(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """A right and a wrong answer get identical replies; a resubmit changes nothing."""
    org, (right, wrong) = await make_org(pg_session_factory, "Right", "Wrong")
    quiz_id = await add_quiz(pg_session_factory, org)
    url = f"{QUIZ}/{quiz_id}/answers"
    good = await client.post(url, json={"response": CORRECT}, headers=as_user(right, org))
    bad = await client.post(url, json={"response": WRONG}, headers=as_user(wrong, org))
    assert good.status_code == bad.status_code == 200
    assert good.json() == bad.json() == {"accepted": True, "alreadyAnswered": False}
    retry = await client.post(url, json={"response": WRONG}, headers=as_user(right, org))
    assert retry.json() == {"accepted": True, "alreadyAnswered": True}
    async with pg_session_factory() as db:
        rows = (await db.execute(select(QuizAnswer).where(QuizAnswer.org_id == org))).scalars()
        stored = {row.user_id: (row.response, row.is_correct) for row in rows}
    assert stored == {right: (CORRECT, True), wrong: (WRONG, False)}
    active = await client.get(f"{QUIZ}/active", headers=as_user(right, org))
    assert active.json()["alreadyAnswered"] is True


async def test_reveal_is_refused_until_the_window_closes(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """Before reveal time the answer endpoint is 403, whether or not you answered."""
    org, (dev,) = await make_org(pg_session_factory, "Dev")
    quiz_id = await add_quiz(pg_session_factory, org)
    await client.post(
        f"{QUIZ}/{quiz_id}/answers", json={"response": CORRECT}, headers=as_user(dev, org)
    )
    early = await client.get(f"{QUIZ}/{quiz_id}/reveal", headers=as_user(dev, org))
    assert early.status_code == 403
    assert "correct_index" not in early.text


async def test_after_the_window_the_answer_and_your_result_are_shown(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """A closed quiz reveals the key, the stats and your own answer; late answers are 409."""
    org, (dev, late) = await make_org(pg_session_factory, "Dev", "Late")
    quiz_id = await add_quiz(pg_session_factory, org, opened_hours_ago=30, closes_in_hours=-6)
    closed = await client.post(
        f"{QUIZ}/{quiz_id}/answers", json={"response": CORRECT}, headers=as_user(late, org)
    )
    assert closed.status_code == 409
    assert (await client.get(f"{QUIZ}/active", headers=as_user(dev, org))).json() is None
    revealed = await client.get(f"{QUIZ}/{quiz_id}/reveal", headers=as_user(dev, org))
    assert revealed.status_code == 200, revealed.text
    body = revealed.json()
    assert body["answerKey"] == {"correct_index": 1} and body["explanation"] == EXPLANATION
    assert (body["totalAnswers"], body["yourAnswer"]) == (0, None)


async def test_a_quiz_that_has_not_opened_yet_is_hidden_and_closed(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """A future window is not active, cannot be answered and cannot be revealed."""
    org, (dev,) = await make_org(pg_session_factory, "Dev")
    quiz_id = await add_quiz(pg_session_factory, org, opened_hours_ago=-2, closes_in_hours=5)
    headers = as_user(dev, org)
    assert (await client.get(f"{QUIZ}/active", headers=headers)).json() is None
    early = await client.post(
        f"{QUIZ}/{quiz_id}/answers", json={"response": CORRECT}, headers=headers
    )
    assert early.status_code == 409
    assert (await client.get(f"{QUIZ}/{quiz_id}/reveal", headers=headers)).status_code == 403


async def test_another_orgs_quiz_cannot_be_seen_answered_or_revealed(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """Quiz ids from another org are 404 even after that org's reveal time."""
    org, (dev,) = await make_org(pg_session_factory, "Dev")
    other, _ = await make_org(pg_session_factory)
    open_id = await add_quiz(pg_session_factory, other)
    headers = as_user(dev, org)
    assert (await client.get(f"{QUIZ}/active", headers=headers)).json() is None
    answer = await client.post(
        f"{QUIZ}/{open_id}/answers", json={"response": CORRECT}, headers=headers
    )
    assert answer.status_code == 404
    assert (await client.get(f"{QUIZ}/{open_id}/reveal", headers=headers)).status_code == 404


async def test_a_correct_answer_earns_quiz_points_not_xp(
    client: AsyncClient, pg_session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After the reveal, the monthly board and recap count the answer; no XP or SP."""
    use_test_db(monkeypatch, pg_session_factory)
    org, (dev,) = await make_org(pg_session_factory, "Dev")
    headers = as_user(dev, org)
    quiz_id = await add_quiz(pg_session_factory, org)
    active = await client.get(f"{QUIZ}/active", headers=headers)
    # Points belong to the month of the quiz's date, not of the answer.
    month = active.json()["quizDate"][:7]
    await client.post(f"{QUIZ}/{quiz_id}/answers", json={"response": CORRECT}, headers=headers)
    # While open, the recap (closed quizzes only) does not list it.
    recap = await client.get(f"{QUIZ}/recap", params={"month": month}, headers=headers)
    assert recap.json()["items"] == []
    await close_quiz(pg_session_factory, quiz_id)
    # Points reach the monthly board at the scheduler's reveal pass, not at submit.
    await reveal_pass(org)
    assert await org_reward_count(pg_session_factory, org) == (0, 0)
    async with pg_session_factory() as db:
        answer = (
            await db.execute(select(QuizAnswer).where(QuizAnswer.org_id == org))
        ).scalar_one()
    board = await client.get(f"{QUIZ}/leaderboard", params={"month": month}, headers=headers)
    assert [(e["userId"], e["correctCount"]) for e in board.json()] == [(str(dev), 1)]
    assert board.json()[0]["totalPoints"] == answer.points_awarded > 0
    recap = await client.get(f"{QUIZ}/recap", params={"month": month}, headers=headers)
    (item,) = recap.json()["items"]
    assert (item["correctAnswer"], item["youCorrect"]) == (CHOICES[1], True)


async def test_the_review_queue_with_answers_is_for_quiz_masters_only(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """A player cannot read the question pool; a quiz master can."""
    org, (player, master) = await make_org(pg_session_factory, "Player", "Master")
    await give_role(pg_session_factory, org, master, "quiz_master")
    assert (await client.get(f"{QUIZ}/review", headers=as_user(player, org))).status_code == 403
    assert (await client.get(f"{QUIZ}/review", headers=as_user(master, org))).status_code == 200
