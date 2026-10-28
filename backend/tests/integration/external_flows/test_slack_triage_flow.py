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

"""Slack intake end to end: a 🧠 reaction, the triage agent, a PM's ✅, a BUD.

Each step is a signed Slack event over HTTP; the queued triage job runs
inline; the agent is the scripted CLI whose MCP calls hit the real route;
every thread reply lands in the fake Slack workspace.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.models.triage_session import TriageStatus
from app.repositories.bud import BUDRepository
from tests.fakes.claude_runner import FakeClaudeRunner
from tests.fakes.claude_script import ToolCall
from tests.fakes.seed import Factory, SeededOrg, seed_member
from tests.fakes.slack import FakeSlack
from tests.integration.external_flows.jobs_support import InlineJobs
from tests.integration.external_flows.slack_support import (
    link_slack,
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
REQUEST = "Merchants keep asking to refund straight to the customer's wallet."
SUMMARY = "*Wallet refunds* for merchants. Priority: high."


async def _summarised(
    client: AsyncClient,
    factory: Factory,
    slack: FakeSlack,
    agent: FakeClaudeRunner,
    jobs: InlineJobs,
) -> tuple[SeededOrg, str]:
    """Brain-react a request and let the agent summarise it; return (org, message ts)."""
    org = await triage_org(factory, slack)
    requester = slack_user_id()
    slack.add_user(requester, "Riya Shah", "riya@acme.dev")
    ts = say_in_channel(slack, requester, REQUEST)
    agent.enqueue(
        triage_reply(
            "summary",
            ToolCall("check_feature_exists", {"feature_description": "refund to wallet"}),
            feature_name="Wallet refunds",
            priority="high",
            message=SUMMARY,
            context={"user_impact": "Refunds land in minutes, not days."},
        )
    )
    assert (await post_event(client, slack, reaction(requester, "brain", ts))).status_code == 200
    await jobs.run_all()
    return org, ts


async def test_a_brain_reaction_triages_the_request_into_a_summary_awaiting_a_pm(
    client: AsyncClient,
    app_sessions: Factory,
    slack: FakeSlack,
    mcp_claude: FakeClaudeRunner,
    triage_jobs: InlineJobs,
) -> None:
    org, ts = await _summarised(client, app_sessions, slack, mcp_claude, triage_jobs)

    (eyes,) = slack.calls_to("reactions.add")
    assert (eyes.args["name"], eyes.args["timestamp"]) == ("eyes", ts)
    assert thread_texts(slack, ts) == [
        "🔍 Analyzing this feature request...",
        "_⏳ Checking for existing features and BUDs..._",
        SUMMARY,
    ]
    session = await session_for(app_sessions, org.org_id, ts)
    assert session is not None
    assert (session.status, session.feature_name, session.priority) == (
        TriageStatus.AWAITING_PM,
        "Wallet refunds",
        "high",
    )
    assert session.requester_name == "Riya Shah"
    assert session.summary_msg_ts == slack.threads[ts][-1]["ts"]
    (run,) = mcp_claude.runs
    assert REQUEST in run.prompt
    assert set(run.mcp_tools) == {"check_feature_exists", "get_bud_context", "search_bugs"}
    (check,) = mcp_claude.tool_calls("check_feature_exists")
    assert (check.status_code, check.is_error) == (200, False)
    assert {call.token for call in slack.calls} == {"xoxb-fake-bot-token"}


async def test_a_pms_approval_turns_the_summary_into_a_bud(
    client: AsyncClient,
    app_sessions: Factory,
    slack: FakeSlack,
    mcp_claude: FakeClaudeRunner,
    triage_jobs: InlineJobs,
) -> None:
    org, ts = await _summarised(client, app_sessions, slack, mcp_claude, triage_jobs)
    pm, pm_slack = await seed_member(app_sessions, org.org_id, "pm", role="pm"), slack_user_id()
    await link_slack(app_sessions, pm, pm_slack)
    session = await session_for(app_sessions, org.org_id, ts)
    assert session is not None and session.summary_msg_ts is not None

    approve = reaction(pm_slack, "white_check_mark", session.summary_msg_ts)
    assert (await post_event(client, slack, approve)).status_code == 200
    await triage_jobs.run_all()

    done = await session_for(app_sessions, org.org_id, ts)
    assert done is not None and done.status == TriageStatus.BUD_CREATED
    assert done.bud_id is not None
    async with app_sessions() as db:
        bud = await BUDRepository(db, org_id=org.org_id).get_by_id(done.bud_id)
    assert bud is not None
    assert (bud.title, (bud.metadata_ or {})["source"]) == ("Wallet refunds", "slack_triage")
    assert "Refunds land in minutes" in (bud.requirements_md or "")
    created = thread_texts(slack, ts)[-1]
    assert created.startswith(f"✅ *BUD-{bud.bud_number:03d}* created: *Wallet refunds*")
    assert f"<@{pm_slack}>" in created


async def test_a_reply_in_the_thread_continues_the_interview(
    client: AsyncClient,
    app_sessions: Factory,
    slack: FakeSlack,
    mcp_claude: FakeClaudeRunner,
    triage_jobs: InlineJobs,
) -> None:
    org = await triage_org(app_sessions, slack)
    requester = slack_user_id()
    ts = say_in_channel(slack, requester, REQUEST)
    mcp_claude.enqueue(
        triage_reply("question", message="Which merchants need this first?"),
        triage_reply("summary", feature_name="Wallet refunds", priority="medium", message=SUMMARY),
    )
    await post_event(client, slack, reaction(requester, "brain", ts))
    await triage_jobs.run_all()

    reply = thread_reply(slack, requester, "Only UK merchants on the new plan.", ts)
    assert (await post_event(client, slack, reply)).status_code == 200
    await triage_jobs.run_all()

    assert thread_texts(slack, ts)[2:] == [
        "Which merchants need this first?",
        "_🤔 Reviewing your response..._",
        SUMMARY,
    ]
    assert "Only UK merchants on the new plan." in mcp_claude.runs[1].prompt
    session = await session_for(app_sessions, org.org_id, ts)
    assert session is not None and session.status == TriageStatus.AWAITING_PM


async def test_a_non_pm_cannot_approve_and_no_bud_is_created(
    client: AsyncClient,
    app_sessions: Factory,
    slack: FakeSlack,
    mcp_claude: FakeClaudeRunner,
    triage_jobs: InlineJobs,
) -> None:
    org, ts = await _summarised(client, app_sessions, slack, mcp_claude, triage_jobs)
    dev, dev_slack = await seed_member(app_sessions, org.org_id, "dev"), slack_user_id()
    await link_slack(app_sessions, dev, dev_slack)
    session = await session_for(app_sessions, org.org_id, ts)
    assert session is not None and session.summary_msg_ts is not None

    approve = reaction(dev_slack, "white_check_mark", session.summary_msg_ts)
    await post_event(client, slack, approve)
    await triage_jobs.run_all()

    assert thread_texts(slack, ts)[-1] == "⚠️ Only PMs and org owners can approve feature requests."
    after = await session_for(app_sessions, org.org_id, ts)
    assert after is not None and (after.status, after.bud_id) == (TriageStatus.AWAITING_PM, None)


async def test_a_pm_rejection_closes_the_session(
    client: AsyncClient,
    app_sessions: Factory,
    slack: FakeSlack,
    mcp_claude: FakeClaudeRunner,
    triage_jobs: InlineJobs,
) -> None:
    org, ts = await _summarised(client, app_sessions, slack, mcp_claude, triage_jobs)
    owner_slack = slack_user_id()
    await link_slack(app_sessions, org.owner_id, owner_slack)
    session = await session_for(app_sessions, org.org_id, ts)
    assert session is not None and session.summary_msg_ts is not None

    await post_event(client, slack, reaction(owner_slack, "x", session.summary_msg_ts))
    await triage_jobs.run_all()

    assert thread_texts(slack, ts)[-1] == f"❌ Feature request declined by <@{owner_slack}>."
    after = await session_for(app_sessions, org.org_id, ts)
    assert after is not None and (after.status, after.bud_id) == (TriageStatus.REJECTED, None)
