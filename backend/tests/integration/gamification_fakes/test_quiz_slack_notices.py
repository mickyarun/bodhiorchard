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

"""Quiz Slack DMs on the fake workspace: who gets them, and that Slack can't stop a quiz."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.models.quiz import QuizStatus
from app.models.quiz_question import QuizQuestionStatus
from app.schemas.settings import QuizGameSettings
from app.services.quiz_scheduler import _open_pass, _reveal_pass
from tests.fakes.seed import Factory, seed_member, seed_org
from tests.fakes.slack import FakeSlack
from tests.integration.gamification_fakes.quiz_fake_support import (
    add_question,
    enable_quiz,
    link_slack,
    open_quiz,
    quizzes,
)

pytestmark = pytest.mark.integration

FIRE = datetime(2026, 3, 2, 10, 0, tzinfo=UTC)
CONFIG: dict[str, Any] = {
    "timezone": "UTC",
    "quizTime": "10:00",
    "activeWeekdays": [0, 1, 2, 3, 4],
    "windowMinutes": 60,
    "monthlySpAmount": 2.0,
    "slackNotifyReveal": True,
}
SETTINGS = QuizGameSettings.model_validate(CONFIG)


async def _org_with_members(factory: Factory, slack: FakeSlack) -> tuple[uuid.UUID, list[str]]:
    """An org on the fake workspace: two reachable members, one opted out, one unlinked."""
    org = await seed_org(factory, slack=slack)
    await enable_quiz(factory, org.org_id, **CONFIG)
    reachable = []
    for name, prefs in [("ana", None), ("ben", None), ("cy", {"quiz": False})]:
        user = await seed_member(factory, org.org_id, name)
        slack_id = f"U{name.upper()}{user.hex[:4]}"
        await link_slack(factory, user, slack_id, prefs)
        if prefs is None:
            reachable.append(slack_id)
    await seed_member(factory, org.org_id, "dee")
    await add_question(factory, org.org_id, QuizQuestionStatus.APPROVED)
    return org.org_id, sorted(reachable)


def _opened_for(slack: FakeSlack) -> list[str]:
    return sorted(str(call.args["users"]) for call in slack.calls_to("conversations.open"))


def _delivered_to(slack: FakeSlack) -> set[str]:
    """DM channels holding at least one delivered message."""
    return {channel for channel in slack.threads if channel.startswith("D")}


def _first_target(slack: FakeSlack, failure: str) -> str:
    """The DM channel of the member whose Slack call was made to fail."""
    if failure == "open-fails":
        return f"D{slack.calls_to('conversations.open')[0].args['users']}"
    return str(slack.calls_to("chat.postMessage")[0].args["channel"])


async def test_opening_dms_every_reachable_member_with_the_prize(
    app_sessions: Factory, fake_slack: FakeSlack
) -> None:
    org_id, reachable = await _org_with_members(app_sessions, fake_slack)

    await _open_pass(org_id, SETTINGS, FIRE)

    assert _opened_for(fake_slack) == reachable
    texts = fake_slack.posted_texts()
    assert len(texts) == 2
    assert all("Today's company quiz is live" in t and "*2 SP*" in t for t in texts)
    assert {c.token for c in fake_slack.calls} == {"xoxb-fake-bot-token"}


@pytest.mark.parametrize("failure", ["post-fails", "rate-limited", "open-fails"])
async def test_a_slack_failure_never_stops_the_quiz_or_the_other_dms(
    app_sessions: Factory, fake_slack: FakeSlack, failure: str
) -> None:
    org_id, reachable = await _org_with_members(app_sessions, fake_slack)
    if failure == "post-fails":
        fake_slack.fail("chat.postMessage", "channel_not_found")
    elif failure == "rate-limited":
        fake_slack.rate_limit("chat.postMessage")
    else:
        fake_slack.fail("conversations.open", "user_not_found")

    await _open_pass(org_id, SETTINGS, FIRE)

    assert [q.status for q in await quizzes(app_sessions, org_id)] == [QuizStatus.OPEN]
    assert _opened_for(fake_slack) == reachable
    everyone = {f"D{slack_id}" for slack_id in reachable}
    others = everyone - {_first_target(fake_slack, failure)}
    assert len(others) == 1
    assert others <= _delivered_to(fake_slack) <= everyone


async def test_an_org_without_a_slack_token_opens_silently(
    app_sessions: Factory, fake_slack: FakeSlack
) -> None:
    org = await seed_org(app_sessions)
    await enable_quiz(app_sessions, org.org_id, **CONFIG)
    await add_question(app_sessions, org.org_id, QuizQuestionStatus.APPROVED)

    await _open_pass(org.org_id, SETTINGS, FIRE)

    assert len(await quizzes(app_sessions, org.org_id)) == 1
    assert fake_slack.calls == []


async def test_several_quizzes_revealed_in_one_tick_send_one_reveal_dm_each(
    app_sessions: Factory, fake_slack: FakeSlack
) -> None:
    org_id, reachable = await _org_with_members(app_sessions, fake_slack)
    for days_ago in (3, 2, 1):
        start = FIRE - timedelta(days=days_ago)
        await open_quiz(app_sessions, org_id, start, start + timedelta(hours=1))

    await _reveal_pass(org_id, SETTINGS, FIRE)
    await _reveal_pass(org_id, SETTINGS, FIRE + timedelta(minutes=1))

    assert [q.status for q in await quizzes(app_sessions, org_id)] == [QuizStatus.REVEALED] * 3
    assert _opened_for(fake_slack) == reachable
    texts = fake_slack.posted_texts()
    assert len(texts) == 2
    assert all("The quiz answer is in" in t for t in texts)
