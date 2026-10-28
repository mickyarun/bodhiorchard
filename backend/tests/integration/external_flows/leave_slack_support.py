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

"""Leave decided from Slack: a workspace-connected team, signed clicks, the prompts sent."""

from __future__ import annotations

import uuid
from typing import Any

from httpx import AsyncClient, Response

from app.core.encryption import encrypt_secret
from app.models.leave_request import LeaveRequest
from app.models.leave_slack_prompt import LeaveSlackPrompt
from app.models.organization import Organization
from app.repositories.leave_slack_prompt import LeaveSlackPromptRepository
from tests.fakes.seed import SLACK_BOT_TOKEN, SLACK_SIGNING_SECRET, Factory
from tests.fakes.signing import signed_slack_interaction
from tests.fakes.slack import FakeSlack
from tests.integration.external_flows.jobs_support import settle_background
from tests.integration.external_flows.slack_support import link_slack
from tests.integration.leave_support import as_user, future_monday

INTERACTIONS = "/api/v1/slack/interactions"


async def connect_workspace(
    factory: Factory, org_id: uuid.UUID, slack: FakeSlack, members: dict[uuid.UUID, str]
) -> None:
    """Wire the org to the fake workspace and link each member's Slack id."""
    async with factory() as db:
        org = await db.get(Organization, org_id)
        assert org is not None
        org.slack_team_id = slack.team_id
        org.slack_bot_token = encrypt_secret(SLACK_BOT_TOKEN)
        org.slack_signing_secret = encrypt_secret(SLACK_SIGNING_SECRET)
        await db.commit()
    for user_id, slack_id in members.items():
        await link_slack(factory, user_id, slack_id)


async def request_leave(
    client: AsyncClient, org_id: uuid.UUID, user_id: uuid.UUID, leave_type: uuid.UUID
) -> uuid.UUID:
    """Ask for one day of leave over HTTP and let the approver prompts go out."""
    day = future_monday().isoformat()
    body = {"kind": "leave", "leave_type_id": str(leave_type), "start_date": day, "end_date": day}
    made = await client.post("/api/v1/leave/requests", json=body, headers=as_user(user_id, org_id))
    assert made.status_code == 201, made.text
    await settle_background()
    return uuid.UUID(made.json()["id"])


def click(slack: FakeSlack, user: str, action: str, request_id: uuid.UUID) -> dict[str, Any]:
    """A ``block_actions`` payload for an Approve / Reject button in a DM."""
    return {
        "type": "block_actions",
        "team": {"id": slack.team_id},
        "user": {"id": user},
        "channel": {"id": f"D{user}"},
        "trigger_id": f"trigger-{uuid.uuid4().hex[:8]}",
        "actions": [{"action_id": action, "value": str(request_id)}],
    }


def reject_note(slack: FakeSlack, user: str, request_id: uuid.UUID, note: str) -> dict[str, Any]:
    """The rejection modal submitted with ``note``."""
    return {
        "type": "view_submission",
        "team": {"id": slack.team_id},
        "user": {"id": user},
        "view": {
            "callback_id": "leave_reject_note",
            "private_metadata": str(request_id),
            "state": {"values": {"note": {"note_input": {"value": note}}}},
        },
    }


async def interact(
    client: AsyncClient, payload: dict[str, Any], *, secret: str = SLACK_SIGNING_SECRET
) -> Response:
    """POST one signed interaction, then let the background Slack sends finish."""
    body, headers = signed_slack_interaction(secret, payload)
    resp = await client.post(INTERACTIONS, content=body, headers=headers)
    await settle_background()
    return resp


async def prompts(
    factory: Factory, org_id: uuid.UUID, request_id: uuid.UUID
) -> list[LeaveSlackPrompt]:
    """The approver prompts recorded for a request."""
    async with factory() as db:
        return await LeaveSlackPromptRepository(db, org_id=org_id).for_request(request_id)


async def leave_request(factory: Factory, request_id: uuid.UUID) -> LeaveRequest:
    """The request row as it is now."""
    async with factory() as db:
        row = await db.get(LeaveRequest, request_id)
        assert row is not None
        return row


def outcome_of(update_args: dict[str, Any]) -> str:
    """The outcome line a ``chat.update`` put in place of the buttons."""
    blocks = update_args["blocks"]
    return str(blocks[-1]["elements"][0]["text"])
