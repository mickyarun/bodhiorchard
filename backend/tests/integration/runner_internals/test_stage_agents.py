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

"""Each BUD stage agent end to end: trigger → worker → scripted agent → stored result."""

from __future__ import annotations

import uuid

import pytest

from app.models.bud import BUDStatus
from app.models.bud_agent_task import AgentTaskStatus
from app.schemas.jobs import JobState
from tests.fakes.claude_runner import FakeClaudeRunner
from tests.fakes.claude_script import AgentScript, ToolCall
from tests.fakes.git_repo import LocalGitRepo
from tests.fakes.seed import Factory, seed_repo
from tests.integration.runner_internals.output_support import (
    TECH_SPEC,
    json_fence,
    planned_feature,
    stage_runs,
    tech_arch_output,
    versions,
)
from tests.integration.runner_internals.runtime_support import JobRuntime
from tests.integration.runner_internals.stage_support import (
    activity,
    activity_types,
    add_bud,
    load_bud,
    load_task,
    seed_agent_org,
    timeline,
    trigger_stage,
)

pytestmark = pytest.mark.integration


async def test_requirements_agent_writes_the_bud_through_mcp(
    stage_claude: FakeClaudeRunner, app_sessions: Factory, job_runtime: JobRuntime
) -> None:
    """The PM skill's ``write_bud`` call lands the body; the task completes."""
    org = await seed_agent_org(app_sessions)
    bud = await add_bud(app_sessions, org.org_id, requirements_md="refunds pls")
    body = "## Problem\n\nShoppers cannot refund.\n\n## Acceptance\n\n- refund within 30 days"
    write = {"bud_number": bud.bud_number, "title": bud.title, "requirements_md": body}
    stage_claude.enqueue(
        AgentScript.ok(
            "Saved the requirements.",
            ToolCall("get_bud_context", {"limit": 5}),
            ToolCall("write_bud", write),
        )
    )

    run = await trigger_stage(app_sessions, org.org_id, bud.id, "bud")
    job = await job_runtime.wait(run.job_id)

    assert (job.state, job.progress_pct) == (JobState.COMPLETED, 100)
    assert (await load_bud(app_sessions, org.org_id, bud.id)).requirements_md == body
    task = await load_task(app_sessions, run.task_id)
    assert task.status == AgentTaskStatus.COMPLETED
    assert task.result_summary == {
        "section": "requirements_md",
        "output_length": len("Saved the requirements."),
        "linked_feature_count": 0,
    }
    assert [c.status_code for c in stage_claude.tool_calls()] == [200, 200]
    (agent_run,) = stage_runs(stage_claude)
    assert agent_run.mcp_tools == [
        "get_bud_context",
        "get_features",
        "write_bud",
        "get_team_context",
    ]
    rows = await activity(app_sessions, org.org_id, bud.id)
    assert activity_types(rows) == ["skill_invoked", "skill_completed"]
    events = [e.event_type for e in await timeline(app_sessions, org.org_id, bud.id)]
    assert events[-1] == "ai_agent_completed"


async def test_requirements_fence_links_only_real_features_of_the_org(
    stage_claude: FakeClaudeRunner, app_sessions: Factory, job_runtime: JobRuntime
) -> None:
    """Unparseable and foreign ids in the fence are dropped; the real one links."""
    org = await seed_agent_org(app_sessions)
    other = await seed_agent_org(app_sessions)
    mine = await planned_feature(app_sessions, org.org_id, "Order history")
    theirs = await planned_feature(app_sessions, other.org_id, "Their feature")
    bud = await add_bud(app_sessions, org.org_id)
    ids = [str(mine), "not-a-uuid", str(theirs), str(uuid.uuid4())]
    stage_claude.enqueue(AgentScript.ok("Linked.\n\n" + json_fence({"linked_feature_ids": ids})))

    run = await trigger_stage(app_sessions, org.org_id, bud.id, "bud")
    await job_runtime.wait(run.job_id)

    task = await load_task(app_sessions, run.task_id)
    assert task.result_summary is not None
    assert task.result_summary["linked_feature_count"] == 1
    events = await timeline(app_sessions, org.org_id, bud.id)
    (linked,) = [e for e in events if e.event_type == "features_auto_linked"]
    assert linked.actor_name == "PM Agent"
    assert linked.detail is not None
    assert (linked.detail["feature_ids"], linked.detail["source"]) == ([str(mine)], "pm_agent")


async def test_requirements_prose_is_kept_when_the_bud_was_empty(
    stage_claude: FakeClaudeRunner, app_sessions: Factory, job_runtime: JobRuntime
) -> None:
    """No ``write_bud`` call on an empty BUD: the prose is stored, fence and insight dropped."""
    org = await seed_agent_org(app_sessions)
    bud = await add_bud(app_sessions, org.org_id, requirements_md=None)
    prose = "## Problem\n\nShoppers cannot refund."
    fence = json_fence({"linked_feature_ids": []})
    stage_claude.enqueue(AgentScript.ok(f"{prose}\n\n{fence}").with_insight())

    run = await trigger_stage(app_sessions, org.org_id, bud.id, "bud")
    await job_runtime.wait(run.job_id)

    assert (await load_bud(app_sessions, org.org_id, bud.id)).requirements_md == prose
    (snapshot,) = await versions(app_sessions, bud.id)
    assert (snapshot.source, snapshot.phase) == ("agent", BUDStatus.BUD)


async def test_tech_arch_stores_the_spec_and_matches_impacted_repos(
    stage_claude: FakeClaudeRunner,
    app_sessions: Factory,
    job_runtime: JobRuntime,
    git_repo: LocalGitRepo,
) -> None:
    """The JSON fence is parsed against tracked repos and stripped from the spec."""
    org = await seed_agent_org(app_sessions)
    repo_id = await seed_repo(app_sessions, org.org_id, git_repo)
    bud = await add_bud(app_sessions, org.org_id, status=BUDStatus.TECH_ARCH)
    output = tech_arch_output("SHOP-API", "ghost-repo")
    stage_claude.enqueue(AgentScript.ok(output, ToolCall("get_bud_context", {"limit": 3})))

    run = await trigger_stage(app_sessions, org.org_id, bud.id, "tech_arch")
    job = await job_runtime.wait(run.job_id)

    assert job.state == JobState.COMPLETED
    stored = await load_bud(app_sessions, org.org_id, bud.id)
    assert stored.tech_spec_md == TECH_SPEC
    assert stored.impacted_repos == [{"repo_id": str(repo_id), "repo_name": git_repo.name}]
    (agent_run,) = stage_runs(stage_claude)
    assert agent_run.cwd == str(git_repo.path)
    assert agent_run.flag("--session-id") is not None
    assert (await load_task(app_sessions, run.task_id)).result_summary == {
        "section": "tech_spec_md",
        "output_length": len(output),
    }
