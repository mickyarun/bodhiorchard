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

"""Slack intake when Slack refuses a call or the triage agent misbehaves."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.models.triage_session import TriageStatus
from tests.fakes.claude_runner import FakeClaudeRunner
from tests.fakes.claude_script import AgentScript
from tests.fakes.seed import Factory
from tests.fakes.slack import FakeSlack
from tests.integration.external_flows.jobs_support import InlineJobs
from tests.integration.external_flows.slack_support import (
    post_event,
    reaction,
    say_in_channel,
    session_for,
    slack_user_id,
    thread_reply,
    thread_texts,
    triage_org,
    triage_reply,
)

pytestmark = pytest.mark.integration


async def test_a_missing_history_scope_stops_triage_before_anything_is_posted(
    client: AsyncClient,
    app_sessions: Factory,
    slack: FakeSlack,
    mcp_claude: FakeClaudeRunner,
    triage_jobs: InlineJobs,
) -> None:
    org = await triage_org(app_sessions, slack)
    ts = say_in_channel(slack, "UREQ", "Please add dark mode")
    slack.fail("conversations.history", "missing_scope")

    await post_event(client, slack, reaction("UREQ", "brain", ts))
    await triage_jobs.run_all()

    assert [c.method for c in slack.calls] == ["conversations.history"]
    assert await session_for(app_sessions, org.org_id, ts) is None
    assert mcp_claude.runs == []


async def test_a_rate_limited_first_reply_leaves_no_half_started_session(
    client: AsyncClient,
    app_sessions: Factory,
    slack: FakeSlack,
    mcp_claude: FakeClaudeRunner,
    triage_jobs: InlineJobs,
) -> None:
    org = await triage_org(app_sessions, slack)
    ts = say_in_channel(slack, "UREQ", "Please add dark mode")
    slack.rate_limit("chat.postMessage")

    await post_event(client, slack, reaction("UREQ", "brain", ts))
    await triage_jobs.run_all()

    assert [c.args["name"] for c in slack.calls_to("reactions.add")] == ["eyes"]
    assert len(slack.calls_to("chat.postMessage")) == 1
    assert await session_for(app_sessions, org.org_id, ts) is None
    assert mcp_claude.runs == []


@pytest.mark.parametrize(
    ("script", "reply", "status"),
    [
        (
            AgentScript.crash(1, "boom"),
            "⚠️ Triage is taking longer than expected. A team member will follow up.",
            TriageStatus.INTERVIEWING,
        ),
        (
            AgentScript.malformed("not json at all"),
            "⚠️ Couldn't read the triage response. Please react 🧠 again to retry.",
            TriageStatus.INTERVIEWING,
        ),
        (
            triage_reply("exists", kind="feature", title="Dark mode"),
            "ℹ️ *Dark mode* is already tracked in the product backlog.",
            TriageStatus.REJECTED,
        ),
    ],
    ids=["agent_crash", "unreadable_answer", "already_tracked"],
)
async def test_agent_outcomes_are_explained_in_the_thread(
    script: AgentScript,
    reply: str,
    status: TriageStatus,
    client: AsyncClient,
    app_sessions: Factory,
    slack: FakeSlack,
    mcp_claude: FakeClaudeRunner,
    triage_jobs: InlineJobs,
) -> None:
    org = await triage_org(app_sessions, slack)
    requester = slack_user_id()
    ts = say_in_channel(slack, requester, "Please add dark mode")
    mcp_claude.enqueue(script)

    await post_event(client, slack, reaction(requester, "brain", ts))
    await triage_jobs.run_all()

    assert thread_texts(slack, ts)[-1] == reply
    session = await session_for(app_sessions, org.org_id, ts)
    assert session is not None and session.status == status


async def test_a_reply_after_triage_closed_does_not_wake_the_agent(
    client: AsyncClient,
    app_sessions: Factory,
    slack: FakeSlack,
    mcp_claude: FakeClaudeRunner,
    triage_jobs: InlineJobs,
) -> None:
    await triage_org(app_sessions, slack)
    requester = slack_user_id()
    ts = say_in_channel(slack, requester, "Please add dark mode")
    mcp_claude.enqueue(triage_reply("exists", kind="feature", title="Dark mode"))
    await post_event(client, slack, reaction(requester, "brain", ts))
    await triage_jobs.run_all()
    posted = len(slack.calls_to("chat.postMessage"))

    await post_event(client, slack, thread_reply(slack, requester, "But I need it now", ts))
    await triage_jobs.run_all()

    assert len(mcp_claude.runs) == 1
    assert len(slack.calls_to("chat.postMessage")) == posted
