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

"""Leave clicks from Slack that are refused, and what Slack is told about it."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.models.leave_request import LeaveStatus
from app.services.leave.slack_actions import NOT_LINKED, OPEN_FAILED
from tests.fakes.slack import FakeSlack
from tests.integration.external_flows.leave_slack_support import (
    click,
    interact,
    leave_request,
    request_leave,
    slack_team,
)
from tests.integration.leave_support import Factory

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("clicker", ["UEMP", "UNOBODY"], ids=["own_request", "unlinked"])
async def test_a_click_by_someone_who_cannot_decide_gets_an_ephemeral_refusal(
    clicker: str, client: AsyncClient, app_sessions: Factory, slack: FakeSlack
) -> None:
    org, emp, _, casual = await slack_team(app_sessions, slack, "Mgr")
    request_id = await request_leave(client, org, emp, casual)

    await interact(client, click(slack, clicker, "leave_approve", request_id))

    (refusal,) = slack.calls_to("chat.postEphemeral")
    assert (refusal.args["user"], refusal.args["channel"]) == (clicker, f"D{clicker}")
    expected = NOT_LINKED if clicker == "UNOBODY" else "You can't decide your own request."
    assert refusal.args["text"] == expected
    assert (await leave_request(app_sessions, request_id)).status == LeaveStatus.PENDING
    assert slack.calls_to("chat.update") == []


async def test_an_expired_trigger_tells_the_manager_to_click_reject_again(
    client: AsyncClient, app_sessions: Factory, slack: FakeSlack
) -> None:
    org, emp, _, casual = await slack_team(app_sessions, slack, "Mgr")
    request_id = await request_leave(client, org, emp, casual)
    slack.fail("views.open", "expired_trigger_id")

    await interact(client, click(slack, "UMGR", "leave_reject", request_id))

    (refusal,) = slack.calls_to("chat.postEphemeral")
    assert refusal.args["text"] == OPEN_FAILED
    assert (await leave_request(app_sessions, request_id)).status == LeaveStatus.PENDING


async def test_a_forged_click_is_refused_with_no_slack_traffic(
    client: AsyncClient, app_sessions: Factory, slack: FakeSlack
) -> None:
    org, emp, _, casual = await slack_team(app_sessions, slack, "Mgr")
    request_id = await request_leave(client, org, emp, casual)
    sent = len(slack.calls)

    resp = await interact(
        client, click(slack, "UMGR", "leave_approve", request_id), secret="f" * 32
    )

    assert resp.status_code == 401
    assert len(slack.calls) == sent
    assert (await leave_request(app_sessions, request_id)).status == LeaveStatus.PENDING
