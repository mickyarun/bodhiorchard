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

"""Slack leave decisions that must change nothing: replays, other workspaces, stale forms.

Slack's API and background senders are stubbed; today is frozen.
"""

from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient

from app.models.leave_request import LeaveStatus
from app.services.leave import notify, slack_actions, slack_prompts
from app.services.leave.lifecycle import submit
from tests.integration.leave_edge_support import deactivate, freeze_today, stored
from tests.integration.leave_slack_support import (
    URL,
    click,
    connect_slack,
    reject_note,
    signed,
)
from tests.integration.leave_support import Factory, leave_body, report_to, setup_org

pytestmark = pytest.mark.integration
TODAY, DAY = date(2030, 6, 3), date(2030, 6, 11)


@pytest.fixture
def ephemeral(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """Stub every outbound Slack call; returns the ephemeral-reply mock."""
    freeze_today(monkeypatch, TODAY)
    reply = AsyncMock(return_value="")
    monkeypatch.setattr(slack_actions, "post_ephemeral", reply)
    monkeypatch.setattr(slack_actions, "open_view", AsyncMock(return_value=""))
    monkeypatch.setattr(slack_actions, "refresh_prompts", AsyncMock())
    monkeypatch.setattr(slack_actions, "bot_token", AsyncMock(return_value="xoxb-test"))
    monkeypatch.setattr(notify, "spawn", lambda job: job.close())
    monkeypatch.setattr(slack_actions, "spawn", lambda job: job.close())
    monkeypatch.setattr(slack_prompts, "update_message", AsyncMock(return_value=""))
    return reply


async def _pending(
    factory: Factory, org: uuid.UUID, emp: uuid.UUID, casual: uuid.UUID
) -> uuid.UUID:
    async with factory() as db:
        request, _ = await submit(db, org, emp, leave_body(casual, DAY, DAY))
        await db.commit()
        return request.id


def _replied(reply: AsyncMock) -> str:
    """The text of the one ephemeral reply."""
    reply.assert_awaited_once()
    return str(reply.await_args.args[3]) if reply.await_args else ""


async def test_a_replayed_click_is_refused(
    client: AsyncClient, pg_session_factory: Factory, ephemeral: AsyncMock
) -> None:
    org, (emp, mgr), casual = await setup_org(pg_session_factory, "Emp", "Mgr")
    await report_to(pg_session_factory, org, emp, mgr)
    team = await connect_slack(pg_session_factory, org, {mgr: "UMGR"})
    request_id = await _pending(pg_session_factory, org, emp, casual)
    payload = click(team, "UMGR", "leave_approve", str(request_id))
    # Correctly signed, but ten minutes old.
    body, headers = signed(payload, age_seconds=600)
    assert (await client.post(URL, content=body, headers=headers)).status_code == 401
    assert (await stored(pg_session_factory, request_id)).status == LeaveStatus.PENDING


async def test_another_workspace_cannot_reach_this_orgs_request(
    client: AsyncClient, pg_session_factory: Factory, ephemeral: AsyncMock
) -> None:
    org, (emp, mgr), casual = await setup_org(pg_session_factory, "Emp", "Mgr")
    await report_to(pg_session_factory, org, emp, mgr)
    other, (boss, report), _ = await setup_org(pg_session_factory, "Boss", "Report")
    await report_to(pg_session_factory, other, report, boss)
    await connect_slack(pg_session_factory, org, {mgr: "UMGR"})
    other_team = await connect_slack(pg_session_factory, other, {boss: "UBOSS"})
    request_id = await _pending(pg_session_factory, org, emp, casual)
    body, headers = signed(click(other_team, "UBOSS", "leave_approve", str(request_id)))
    assert (await client.post(URL, content=body, headers=headers)).status_code == 200
    assert (await stored(pg_session_factory, request_id)).status == LeaveStatus.PENDING
    assert _replied(ephemeral) == "Request not found."


async def test_a_reason_form_from_someone_who_cannot_decide_changes_nothing(
    client: AsyncClient, pg_session_factory: Factory, ephemeral: AsyncMock
) -> None:
    org, (emp, mgr, peer), casual = await setup_org(pg_session_factory, "Emp", "Mgr", "Peer")
    await report_to(pg_session_factory, org, emp, mgr)
    team = await connect_slack(pg_session_factory, org, {mgr: "UMGR", peer: "UPEER"})
    request_id = await _pending(pg_session_factory, org, emp, casual)
    body, headers = signed(reject_note(team, "UPEER", request_id, "Not you"))
    answer = (await client.post(URL, content=body, headers=headers)).json()
    assert answer["response_action"] == "errors"
    assert "managers or HR" in answer["errors"]["note"]
    assert (await stored(pg_session_factory, request_id)).status == LeaveStatus.PENDING


async def test_a_reason_form_sent_after_another_approval_is_told_so(
    client: AsyncClient, pg_session_factory: Factory, ephemeral: AsyncMock
) -> None:
    org, (emp, m1, m2), casual = await setup_org(pg_session_factory, "Emp", "M1", "M2")
    await report_to(pg_session_factory, org, emp, m1, m2)
    team = await connect_slack(pg_session_factory, org, {m1: "UM1", m2: "UM2"})
    request_id = await _pending(pg_session_factory, org, emp, casual)
    # M1 opens the reject form; M2 approves while it is open.
    opened, headers = signed(click(team, "UM1", "leave_reject", str(request_id)))
    assert (await client.post(URL, content=opened, headers=headers)).status_code == 200
    approve, headers = signed(click(team, "UM2", "leave_approve", str(request_id)))
    assert (await client.post(URL, content=approve, headers=headers)).status_code == 200
    late, headers = signed(reject_note(team, "UM1", request_id, "Too late"))
    answer = (await client.post(URL, content=late, headers=headers)).json()
    assert answer["errors"]["note"] == "M2 already approved this request."
    decided = await stored(pg_session_factory, request_id)
    assert (decided.status, decided.decided_by, decided.decision_note) == (
        LeaveStatus.APPROVED,
        m2,
        None,
    )


async def test_a_deactivated_managers_click_counts_as_unlinked(
    client: AsyncClient, pg_session_factory: Factory, ephemeral: AsyncMock
) -> None:
    org, (emp, mgr), casual = await setup_org(pg_session_factory, "Emp", "Mgr")
    await report_to(pg_session_factory, org, emp, mgr)
    team = await connect_slack(pg_session_factory, org, {mgr: "UMGR"})
    request_id = await _pending(pg_session_factory, org, emp, casual)
    await deactivate(pg_session_factory, mgr)
    body, headers = signed(click(team, "UMGR", "leave_approve", str(request_id)))
    assert (await client.post(URL, content=body, headers=headers)).status_code == 200
    assert _replied(ephemeral) == slack_actions.NOT_LINKED
    assert (await stored(pg_session_factory, request_id)).status == LeaveStatus.PENDING


@pytest.mark.parametrize(
    ("action", "value"),
    [("leave_approve", "not-a-uuid"), ("leave_open", "{request}"), ("leave_approve", "")],
)
async def test_malformed_or_other_clicks_change_nothing(
    client: AsyncClient,
    pg_session_factory: Factory,
    ephemeral: AsyncMock,
    action: str,
    value: str,
) -> None:
    org, (emp, mgr), casual = await setup_org(pg_session_factory, "Emp", "Mgr")
    await report_to(pg_session_factory, org, emp, mgr)
    team = await connect_slack(pg_session_factory, org, {mgr: "UMGR"})
    request_id = await _pending(pg_session_factory, org, emp, casual)
    payload = click(team, "UMGR", action, value.format(request=request_id))
    body, headers = signed(payload)
    assert (await client.post(URL, content=body, headers=headers)).status_code == 200
    assert (await stored(pg_session_factory, request_id)).status == LeaveStatus.PENDING
    ephemeral.assert_not_awaited()
