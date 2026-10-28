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

"""Signed Slack events, workspace messages, and the triage rows they produce."""

from __future__ import annotations

import json
import uuid
from typing import Any

from httpx import AsyncClient, Response

from app.models.triage_session import TriageSession
from app.models.user import User
from app.repositories.triage_session import TriageSessionRepository
from app.services.skill_loader import seed_skills_for_org
from tests.fakes.claude_script import AgentScript, Step
from tests.fakes.seed import SLACK_SIGNING_SECRET, Factory, SeededOrg, seed_org
from tests.fakes.signing import signed_slack_event
from tests.fakes.slack import FakeSlack

EVENTS = "/api/v1/slack/events"
CHANNEL = "C0PRODUCT"


async def post_event(
    client: AsyncClient,
    slack: FakeSlack,
    event: dict[str, Any],
    *,
    secret: str = SLACK_SIGNING_SECRET,
    timestamp: int | None = None,
    team_id: str | None = None,
) -> Response:
    """POST one signed ``event_callback`` for the fake's workspace."""
    body, headers = signed_slack_event(
        secret, team_id or slack.team_id, event, timestamp=timestamp
    )
    return await client.post(EVENTS, content=body, headers=headers)


def reaction(user: str, name: str, ts: str, channel: str = CHANNEL) -> dict[str, Any]:
    """A ``reaction_added`` event on a channel message."""
    item = {"type": "message", "channel": channel, "ts": ts}
    return {"type": "reaction_added", "user": user, "reaction": name, "item": item}


def thread_reply(
    slack: FakeSlack, user: str, text: str, thread_ts: str, channel: str = CHANNEL
) -> dict[str, Any]:
    """A human reply in a thread: kept in the fake's history, returned as the event."""
    ts = f"1700001000.{uuid.uuid4().int % 1_000_000:06d}"
    slack.threads.setdefault(thread_ts, []).append({"ts": ts, "user": user, "text": text})
    return {
        "type": "message",
        "user": user,
        "text": text,
        "ts": ts,
        "thread_ts": thread_ts,
        "channel": channel,
    }


def say_in_channel(slack: FakeSlack, user: str, text: str, channel: str = CHANNEL) -> str:
    """A top-level message the workspace already has; returns its ``ts``."""
    ts = f"1699999000.{uuid.uuid4().int % 1_000_000:06d}"
    message = {"ts": ts, "user": user, "text": text}
    slack.threads.setdefault(channel, []).append(message)
    slack.threads.setdefault(ts, []).append(message)
    return ts


def thread_texts(slack: FakeSlack, thread_ts: str) -> list[str]:
    """Texts the bot posted into ``thread_ts``, in order."""
    return [
        str(call.args.get("text", ""))
        for call in slack.calls_to("chat.postMessage")
        if call.args.get("thread_ts") == thread_ts
    ]


def triage_reply(action: str, *steps: Step, **data: Any) -> AgentScript:
    """The triage agent answering with ``{"action": ..., "data": ...}``."""
    return AgentScript.ok(json.dumps({"action": action, "data": data}), *steps)


async def triage_org(factory: Factory, slack: FakeSlack) -> SeededOrg:
    """An org wired to the fake workspace, with the agent skills a new org gets."""
    org = await seed_org(factory, slack=slack)
    async with factory() as db:
        await seed_skills_for_org(org.org_id, db)
        await db.commit()
    return org


async def link_slack(factory: Factory, user_id: uuid.UUID, slack_id: str) -> None:
    """Record ``slack_id`` as the member's Slack account."""
    async with factory() as db:
        user = await db.get(User, user_id)
        assert user is not None
        user.slack_id = slack_id
        await db.commit()


async def session_for(
    factory: Factory, org_id: uuid.UUID, ts: str, channel: str = CHANNEL
) -> TriageSession | None:
    """The triage session started from the message at ``ts``."""
    async with factory() as db:
        return await TriageSessionRepository(db, org_id=org_id).get_by_original_msg(channel, ts)


def slack_user_id() -> str:
    """A Slack member id no other test uses."""
    return f"U{uuid.uuid4().hex[:9].upper()}"
