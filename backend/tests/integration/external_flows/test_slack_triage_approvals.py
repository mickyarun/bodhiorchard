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

"""A triage summary that a PM rejects, or that someone without the role tries to approve."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.models.triage_session import TriageStatus
from tests.fakes.claude_runner import FakeClaudeRunner
from tests.fakes.seed import Factory, seed_member
from tests.fakes.slack import FakeSlack
from tests.integration.external_flows.jobs_support import InlineJobs
from tests.integration.external_flows.slack_support import (
    link_slack,
    post_event,
    reaction,
    session_for,
    slack_user_id,
    summarised_request,
    thread_texts,
)

pytestmark = pytest.mark.integration


async def test_a_non_pm_cannot_approve_and_no_bud_is_created(
    client: AsyncClient,
    app_sessions: Factory,
    slack: FakeSlack,
    mcp_claude: FakeClaudeRunner,
    triage_jobs: InlineJobs,
) -> None:
    org, ts = await summarised_request(client, app_sessions, slack, mcp_claude, triage_jobs)
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
    org, ts = await summarised_request(client, app_sessions, slack, mcp_claude, triage_jobs)
    owner_slack = slack_user_id()
    await link_slack(app_sessions, org.owner_id, owner_slack)
    session = await session_for(app_sessions, org.org_id, ts)
    assert session is not None and session.summary_msg_ts is not None

    await post_event(client, slack, reaction(owner_slack, "x", session.summary_msg_ts))
    await triage_jobs.run_all()

    assert thread_texts(slack, ts)[-1] == f"❌ Feature request declined by <@{owner_slack}>."
    after = await session_for(app_sessions, org.org_id, ts)
    assert after is not None and (after.status, after.bud_id) == (TriageStatus.REJECTED, None)
