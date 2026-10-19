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

"""Approving and rejecting leave from Slack buttons, end to end over HTTP.

Requests are signed exactly as Slack signs them. Slack's API and the
background senders are stubbed: nothing leaves the test.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from typing import Any
from unittest.mock import AsyncMock
from urllib.parse import urlencode

import pytest
from httpx import AsyncClient

from app.core.encryption import encrypt_secret
from app.models.leave_request import LeaveRequest, LeaveStatus
from app.models.organization import Organization
from app.models.user import User
from app.services.leave import notify, slack_actions, slack_prompts
from app.services.leave.lifecycle import submit
from tests.integration.leave_support import (
    Factory,
    future_monday,
    leave_body,
    report_to,
    setup_org,
)

pytestmark = pytest.mark.integration
URL = "/api/v1/slack/interactions"
SECRET = "test-signing-secret"


@pytest.fixture
def slack(monkeypatch: pytest.MonkeyPatch) -> dict[str, AsyncMock]:
    """Stub every outbound Slack call and background send."""
    calls = {
        "ephemeral": AsyncMock(return_value=""),
        "open_view": AsyncMock(return_value=""),
        "refresh": AsyncMock(),
    }
    monkeypatch.setattr(slack_actions, "post_ephemeral", calls["ephemeral"])
    monkeypatch.setattr(slack_actions, "open_view", calls["open_view"])
    monkeypatch.setattr(slack_actions, "refresh_prompts", calls["refresh"])
    monkeypatch.setattr(slack_actions, "bot_token", AsyncMock(return_value="xoxb-test"))
    monkeypatch.setattr(notify, "spawn", lambda job: job.close())
    monkeypatch.setattr(slack_actions, "spawn", lambda job: job.close())
    monkeypatch.setattr(slack_prompts, "update_message", AsyncMock(return_value=""))
    return calls


async def _connect(factory: Factory, org: uuid.UUID, slack_ids: dict[uuid.UUID, str]) -> str:
    team = f"T{uuid.uuid4().hex[:8]}"
    async with factory() as db:
        organization = await db.get(Organization, org)
        assert organization is not None
        organization.slack_team_id = team
        organization.slack_signing_secret = encrypt_secret(SECRET)
        organization.slack_bot_token = encrypt_secret("xoxb-test")
        for user_id, slack_id in slack_ids.items():
            user = await db.get(User, user_id)
            assert user is not None
            user.slack_id = slack_id
        await db.commit()
    return team


async def _pending(
    factory: Factory, org: uuid.UUID, emp: uuid.UUID, casual: uuid.UUID
) -> uuid.UUID:
    mon = future_monday()
    async with factory() as db:
        request, _ = await submit(db, org, emp, leave_body(casual, mon, mon))
        await db.commit()
        return request.id


def _signed(payload: dict[str, Any], secret: str = SECRET) -> tuple[bytes, dict[str, str]]:
    body = urlencode({"payload": json.dumps(payload)}).encode()
    ts = str(int(time.time()))
    digest = hmac.new(secret.encode(), f"v0:{ts}:{body.decode()}".encode(), hashlib.sha256)
    headers = {
        "X-Slack-Request-Timestamp": ts,
        "X-Slack-Signature": "v0=" + digest.hexdigest(),
        "Content-Type": "application/x-www-form-urlencoded",
    }
    return body, headers


def _click(team: str, slack_user: str, action: str, request_id: uuid.UUID) -> dict[str, Any]:
    return {
        "type": "block_actions",
        "team": {"id": team},
        "user": {"id": slack_user},
        "channel": {"id": "D1"},
        "trigger_id": "trig",
        "actions": [{"action_id": action, "value": str(request_id)}],
    }


async def _status(factory: Factory, request_id: uuid.UUID) -> LeaveRequest:
    async with factory() as db:
        request = await db.get(LeaveRequest, request_id)
        assert request is not None
        return request


async def test_a_manager_approves_from_slack(
    client: AsyncClient, pg_session_factory: Factory, slack: dict[str, AsyncMock]
) -> None:
    org, (emp, mgr), casual = await setup_org(pg_session_factory, "Emp", "Mgr")
    await report_to(pg_session_factory, org, emp, mgr)
    team = await _connect(pg_session_factory, org, {mgr: "UMGR", emp: "UEMP"})
    request_id = await _pending(pg_session_factory, org, emp, casual)
    body, headers = _signed(_click(team, "UMGR", "leave_approve", request_id))
    assert (await client.post(URL, content=body, headers=headers)).status_code == 200
    decided = await _status(pg_session_factory, request_id)
    assert (decided.status, decided.decided_by) == (LeaveStatus.APPROVED, mgr)
    slack["ephemeral"].assert_not_awaited()


async def test_unsigned_or_forged_clicks_change_nothing(
    client: AsyncClient, pg_session_factory: Factory, slack: dict[str, AsyncMock]
) -> None:
    org, (emp, mgr), casual = await setup_org(pg_session_factory, "Emp", "Mgr")
    await report_to(pg_session_factory, org, emp, mgr)
    team = await _connect(pg_session_factory, org, {mgr: "UMGR"})
    request_id = await _pending(pg_session_factory, org, emp, casual)
    forged, headers = _signed(_click(team, "UMGR", "leave_approve", request_id), "wrong-secret")
    assert (await client.post(URL, content=forged, headers=headers)).status_code == 401
    body, _ = _signed(_click(team, "UMGR", "leave_approve", request_id))
    assert (await client.post(URL, content=body)).status_code == 401
    assert (await _status(pg_session_factory, request_id)).status == LeaveStatus.PENDING


@pytest.mark.parametrize("clicker", ["peer", "requester", "unlinked"])
async def test_only_an_approver_can_decide_from_slack(
    clicker: str,
    client: AsyncClient,
    pg_session_factory: Factory,
    slack: dict[str, AsyncMock],
) -> None:
    org, (emp, mgr, peer), casual = await setup_org(pg_session_factory, "Emp", "Mgr", "Peer")
    await report_to(pg_session_factory, org, emp, mgr)
    team = await _connect(pg_session_factory, org, {emp: "UEMP", peer: "UPEER"})
    request_id = await _pending(pg_session_factory, org, emp, casual)
    slack_user = {"peer": "UPEER", "requester": "UEMP", "unlinked": "UNOBODY"}[clicker]
    body, headers = _signed(_click(team, slack_user, "leave_approve", request_id))
    assert (await client.post(URL, content=body, headers=headers)).status_code == 200
    assert (await _status(pg_session_factory, request_id)).status == LeaveStatus.PENDING
    slack["ephemeral"].assert_awaited_once()


async def test_reject_asks_why_then_records_the_note(
    client: AsyncClient, pg_session_factory: Factory, slack: dict[str, AsyncMock]
) -> None:
    org, (emp, mgr), casual = await setup_org(pg_session_factory, "Emp", "Mgr")
    await report_to(pg_session_factory, org, emp, mgr)
    team = await _connect(pg_session_factory, org, {mgr: "UMGR"})
    request_id = await _pending(pg_session_factory, org, emp, casual)
    body, headers = _signed(_click(team, "UMGR", "leave_reject", request_id))
    assert (await client.post(URL, content=body, headers=headers)).status_code == 200
    slack["open_view"].assert_awaited_once()
    assert (await _status(pg_session_factory, request_id)).status == LeaveStatus.PENDING

    def submission(note: str) -> dict[str, Any]:
        return {
            "type": "view_submission",
            "team": {"id": team},
            "user": {"id": "UMGR"},
            "view": {
                "callback_id": "leave_reject_note",
                "private_metadata": str(request_id),
                "state": {"values": {"note": {"note_input": {"value": note}}}},
            },
        }

    body, headers = _signed(submission(" "))
    blank = await client.post(URL, content=body, headers=headers)
    assert blank.json()["response_action"] == "errors"
    body, headers = _signed(submission("Release week, sorry"))
    assert (await client.post(URL, content=body, headers=headers)).status_code == 200
    decided = await _status(pg_session_factory, request_id)
    assert (decided.status, decided.decision_note) == (LeaveStatus.REJECTED, "Release week, sorry")


async def test_a_second_click_says_it_was_already_decided(
    client: AsyncClient, pg_session_factory: Factory, slack: dict[str, AsyncMock]
) -> None:
    org, (emp, m1, m2), casual = await setup_org(pg_session_factory, "Emp", "M1", "M2")
    await report_to(pg_session_factory, org, emp, m1, m2)
    team = await _connect(pg_session_factory, org, {m1: "UM1", m2: "UM2"})
    request_id = await _pending(pg_session_factory, org, emp, casual)
    for slack_user in ("UM1", "UM2"):
        body, headers = _signed(_click(team, slack_user, "leave_approve", request_id))
        await client.post(URL, content=body, headers=headers)
    assert (await _status(pg_session_factory, request_id)).decided_by == m1
    slack["ephemeral"].assert_awaited_once()
    slack["refresh"].assert_called()
