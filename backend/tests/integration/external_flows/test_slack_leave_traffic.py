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

"""Leave approvals in Slack, judged by the Slack traffic they cause.

Nothing on the Slack side is stubbed: the approver prompt, the button
clicks, the ``chat.update`` that swaps the buttons for the outcome, the DM
to the requester and the ephemeral refusals all go through the fake
workspace, and the background senders run to completion before asserting.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.models.leave_request import LeaveStatus
from tests.fakes.slack import FakeSlack
from tests.integration.external_flows.leave_slack_support import (
    click,
    interact,
    leave_request,
    outcome_of,
    prompts,
    reject_note,
    request_leave,
    slack_team,
)
from tests.integration.leave_support import Factory

pytestmark = pytest.mark.integration


async def test_a_new_request_sends_the_manager_a_prompt_with_buttons(
    client: AsyncClient, app_sessions: Factory, slack: FakeSlack
) -> None:
    org, emp, people, casual = await slack_team(app_sessions, slack, "Mgr")

    request_id = await request_leave(client, org, emp, casual)

    assert [c.args["users"] for c in slack.calls_to("conversations.open")] == ["UMGR"]
    (prompt,) = slack.calls_to("chat.postMessage")
    assert prompt.args["channel"] == "DUMGR"
    buttons = prompt.args["blocks"][-1]["elements"]
    assert [(b["action_id"], b.get("value")) for b in buttons[:2]] == [
        ("leave_approve", str(request_id)),
        ("leave_reject", str(request_id)),
    ]
    (row,) = await prompts(app_sessions, org, request_id)
    assert (row.user_id, row.channel) == (people["Mgr"], "DUMGR")
    assert slack.calls_to("chat.update") == []


async def test_approving_from_slack_updates_the_prompt_and_tells_the_requester(
    client: AsyncClient, app_sessions: Factory, slack: FakeSlack
) -> None:
    org, emp, people, casual = await slack_team(app_sessions, slack, "Mgr")
    request_id = await request_leave(client, org, emp, casual)
    (row,) = await prompts(app_sessions, org, request_id)

    resp = await interact(client, click(slack, "UMGR", "leave_approve", request_id))

    assert resp.status_code == 200
    decided = await leave_request(app_sessions, request_id)
    assert (decided.status, decided.decided_by) == (LeaveStatus.APPROVED, people["Mgr"])
    (update,) = slack.calls_to("chat.update")
    assert (update.args["channel"], update.args["ts"]) == (row.channel, row.ts)
    assert outcome_of(update.args) == "Approved by Mgr"
    dm = [c for c in slack.calls_to("chat.postMessage") if c.args["channel"] == "DUEMP"]
    assert len(dm) == 1 and "was approved by Mgr" in dm[0].args["text"]
    assert slack.calls_to("chat.postEphemeral") == []


async def test_rejecting_opens_a_modal_then_the_note_rejects_and_updates_the_prompt(
    client: AsyncClient, app_sessions: Factory, slack: FakeSlack
) -> None:
    org, emp, _, casual = await slack_team(app_sessions, slack, "Mgr")
    request_id = await request_leave(client, org, emp, casual)
    payload = click(slack, "UMGR", "leave_reject", request_id)

    await interact(client, payload)
    (opened,) = slack.calls_to("views.open")
    assert opened.args["trigger_id"] == payload["trigger_id"]
    assert opened.args["view"]["private_metadata"] == str(request_id)
    assert (await leave_request(app_sessions, request_id)).status == LeaveStatus.PENDING

    resp = await interact(client, reject_note(slack, "UMGR", request_id, "Release week"))

    assert (resp.status_code, resp.content) == (200, b"")
    rejected = await leave_request(app_sessions, request_id)
    assert (rejected.status, rejected.decision_note) == (LeaveStatus.REJECTED, "Release week")
    (update,) = slack.calls_to("chat.update")
    assert outcome_of(update.args) == "Rejected by Mgr"
    dm = [c for c in slack.calls_to("chat.postMessage") if c.args["channel"] == "DUEMP"]
    assert len(dm) == 1 and "was rejected by Mgr" in dm[0].args["text"]


async def test_the_second_manager_is_told_it_was_decided_and_both_prompts_show_it(
    client: AsyncClient, app_sessions: Factory, slack: FakeSlack
) -> None:
    org, emp, people, casual = await slack_team(app_sessions, slack, "Ana", "Ben")
    request_id = await request_leave(client, org, emp, casual)
    assert len(await prompts(app_sessions, org, request_id)) == 2

    await interact(client, click(slack, "UANA", "leave_approve", request_id))
    late = await interact(client, click(slack, "UBEN", "leave_approve", request_id))

    assert late.status_code == 200
    (refusal,) = slack.calls_to("chat.postEphemeral")
    assert (refusal.args["user"], refusal.args["channel"]) == ("UBEN", "DUBEN")
    assert refusal.args["text"] == "Ana already approved this request."
    updated = {(c.args["channel"], outcome_of(c.args)) for c in slack.calls_to("chat.update")}
    assert updated == {("DUANA", "Approved by Ana"), ("DUBEN", "Approved by Ana")}
    decided = await leave_request(app_sessions, request_id)
    assert (decided.status, decided.decided_by) == (LeaveStatus.APPROVED, people["Ana"])


async def test_a_prompt_that_slack_refused_is_not_recorded_but_the_request_stands(
    client: AsyncClient, app_sessions: Factory, slack: FakeSlack
) -> None:
    org, emp, _, casual = await slack_team(app_sessions, slack, "Mgr")
    slack.fail("chat.postMessage", "missing_scope")

    request_id = await request_leave(client, org, emp, casual)

    assert len(slack.calls_to("chat.postMessage")) == 1
    assert await prompts(app_sessions, org, request_id) == []
    assert (await leave_request(app_sessions, request_id)).status == LeaveStatus.PENDING
