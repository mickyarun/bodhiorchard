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

"""Slack interactions signed the way Slack signs them, for the leave Slack tests.

Nothing here talks to Slack: the tests stub every outbound call.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from typing import Any
from urllib.parse import urlencode

from app.core.encryption import encrypt_secret
from app.models.organization import Organization
from app.models.user import User
from tests.integration.leave_support import Factory

SECRET = "test-signing-secret"
URL = "/api/v1/slack/interactions"


async def connect_slack(factory: Factory, org: uuid.UUID, slack_ids: dict[uuid.UUID, str]) -> str:
    """Connect ``org`` to a new Slack workspace and link members; returns the team id."""
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


def signed(payload: dict[str, Any], *, age_seconds: int = 0) -> tuple[bytes, dict[str, str]]:
    """Form body and headers signed with the workspace secret, ``age_seconds`` ago."""
    body = urlencode({"payload": json.dumps(payload)}).encode()
    ts = str(int(time.time()) - age_seconds)
    digest = hmac.new(SECRET.encode(), f"v0:{ts}:{body.decode()}".encode(), hashlib.sha256)
    headers = {
        "X-Slack-Request-Timestamp": ts,
        "X-Slack-Signature": "v0=" + digest.hexdigest(),
        "Content-Type": "application/x-www-form-urlencoded",
    }
    return body, headers


def click(team: str, slack_user: str, action: str, value: str) -> dict[str, Any]:
    """A button click on a leave prompt."""
    return {
        "type": "block_actions",
        "team": {"id": team},
        "user": {"id": slack_user},
        "channel": {"id": "D1"},
        "trigger_id": "trig",
        "actions": [{"action_id": action, "value": value}],
    }


def reject_note(team: str, slack_user: str, request_id: uuid.UUID, note: str) -> dict[str, Any]:
    """The rejection form submitted with ``note``."""
    return {
        "type": "view_submission",
        "team": {"id": team},
        "user": {"id": slack_user},
        "view": {
            "callback_id": "leave_reject_note",
            "private_metadata": str(request_id),
            "state": {"values": {"note": {"note_input": {"value": note}}}},
        },
    }
