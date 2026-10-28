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

import uuid

import pytest
from httpx import AsyncClient

from app.models.leave_request import LeaveStatus
from app.services.leave.slack_actions import NOT_LINKED, OPEN_FAILED
from tests.fakes.slack import FakeSlack
from tests.integration.external_flows.leave_slack_support import (
    click,
    connect_workspace,
    interact,
    leave_request,
    outcome_of,
    prompts,
    reject_note,
    request_leave,
)
from tests.integration.leave_support import Factory, report_to, setup_org

pytestmark = pytest.mark.integration


async def _team(
    factory: Factory, slack: FakeSlack, *managers: str
) -> tuple[uuid.UUID, uuid.UUID, dict[str, uuid.UUID], uuid.UUID]:
    """An employee reporting to ``managers``, all linked to Slack as U<NAME>."""
    org, ids, casual = await setup_org(factory, "Emp", *managers)
    emp, people = ids[0], dict(zip(managers, ids[1:], strict=True))
    await report_to(factory, org, emp, *people.values())
    links = {emp: "UEMP"} | {uid: f"U{name.upper()}" for name, uid in people.items()}
    await connect_workspace(factory, org, slack, links)
    return org, emp, people, casual


async def test_a_new_request_sends_the_manager_a_prompt_with_buttons(
    client: AsyncClient, app_sessions: Factory, slack: FakeSlack
) -> None:
    org, emp, people, casual = await _team(app_sessions, slack, "Mgr")

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
    org, emp, people, casual = await _team(app_sessions, slack, "Mgr")
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
    org, emp, _, casual = await _team(app_sessions, slack, "Mgr")
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
    org, emp, _, casual = await _team(app_sessions, slack, "Ana", "Ben")
    request_id = await request_leave(client, org, emp, casual)
    assert len(await prompts(app_sessions, org, request_id)) == 2

    await interact(client, click(slack, "UANA", "leave_approve", request_id))
    late = await interact(client, click(slack, "UBEN", "leave_approve", request_id))

    assert late.status_code == 200
    (refusal,) = slack.calls_to("chat.postEphemeral")
    assert (refusal.args["user"], refusal.args["channel"]) == ("UBEN", "DUBEN")
    assert "Ana" in refusal.args["text"]
    updated = {(c.args["channel"], outcome_of(c.args)) for c in slack.calls_to("chat.update")}
    assert updated == {("DUANA", "Approved by Ana"), ("DUBEN", "Approved by Ana")}
    assert (await leave_request(app_sessions, request_id)).decided_by is not None


@pytest.mark.parametrize("clicker", ["UEMP", "UNOBODY"], ids=["own_request", "unlinked"])
async def test_a_click_by_someone_who_cannot_decide_gets_an_ephemeral_refusal(
    clicker: str, client: AsyncClient, app_sessions: Factory, slack: FakeSlack
) -> None:
    org, emp, _, casual = await _team(app_sessions, slack, "Mgr")
    request_id = await request_leave(client, org, emp, casual)

    await interact(client, click(slack, clicker, "leave_approve", request_id))

    (refusal,) = slack.calls_to("chat.postEphemeral")
    assert (refusal.args["user"], refusal.args["channel"]) == (clicker, f"D{clicker}")
    if clicker == "UNOBODY":
        assert refusal.args["text"] == NOT_LINKED
    assert (await leave_request(app_sessions, request_id)).status == LeaveStatus.PENDING
    assert slack.calls_to("chat.update") == []


async def test_an_expired_trigger_tells_the_manager_to_click_reject_again(
    client: AsyncClient, app_sessions: Factory, slack: FakeSlack
) -> None:
    org, emp, _, casual = await _team(app_sessions, slack, "Mgr")
    request_id = await request_leave(client, org, emp, casual)
    slack.fail("views.open", "expired_trigger_id")

    await interact(client, click(slack, "UMGR", "leave_reject", request_id))

    (refusal,) = slack.calls_to("chat.postEphemeral")
    assert refusal.args["text"] == OPEN_FAILED
    assert (await leave_request(app_sessions, request_id)).status == LeaveStatus.PENDING


async def test_a_prompt_that_slack_refused_is_not_recorded_but_the_request_stands(
    client: AsyncClient, app_sessions: Factory, slack: FakeSlack
) -> None:
    org, emp, _, casual = await _team(app_sessions, slack, "Mgr")
    slack.fail("chat.postMessage", "missing_scope")

    request_id = await request_leave(client, org, emp, casual)

    assert len(slack.calls_to("chat.postMessage")) == 1
    assert await prompts(app_sessions, org, request_id) == []
    assert (await leave_request(app_sessions, request_id)).status == LeaveStatus.PENDING


async def test_a_forged_click_is_refused_with_no_slack_traffic(
    client: AsyncClient, app_sessions: Factory, slack: FakeSlack
) -> None:
    org, emp, _, casual = await _team(app_sessions, slack, "Mgr")
    request_id = await request_leave(client, org, emp, casual)
    sent = len(slack.calls)

    resp = await interact(
        client, click(slack, "UMGR", "leave_approve", request_id), secret="f" * 32
    )

    assert resp.status_code == 401
    assert len(slack.calls) == sent
    assert (await leave_request(app_sessions, request_id)).status == LeaveStatus.PENDING
