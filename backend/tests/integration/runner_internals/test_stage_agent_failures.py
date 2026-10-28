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

"""Agent runs that fail: the task row, the job and the activity trail all say so."""

from __future__ import annotations

import pytest

from app.models.bud import BUDStatus
from app.models.bud_agent_task import AgentTaskStatus
from app.schemas.jobs import JobState
from tests.fakes.claude_runner import FakeClaudeRunner
from tests.fakes.claude_script import AgentScript, ToolCall
from tests.fakes.seed import Factory
from tests.integration.runner_internals.output_support import stage_runs
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


async def test_non_zero_exit_fails_the_task_with_the_cli_error(
    stage_claude: FakeClaudeRunner, app_sessions: Factory, job_runtime: JobRuntime
) -> None:
    """Exit 2 with stderr: task and job FAILED, ``unknown`` code, BUD untouched."""
    org = await seed_agent_org(app_sessions)
    bud = await add_bud(app_sessions, org.org_id, requirements_md="refunds pls")
    stage_claude.enqueue(AgentScript.crash(exit_code=2, stderr="credit balance too low"))

    run = await trigger_stage(app_sessions, org.org_id, bud.id, "bud")
    job = await job_runtime.wait(run.job_id)

    assert (job.state, job.error_code) == (JobState.FAILED, "unknown")
    assert "exit code 2" in (job.error or "")
    assert "credit balance too low" in (job.error or "")
    task = await load_task(app_sessions, run.task_id)
    assert task.status == AgentTaskStatus.FAILED
    assert task.error_message == (job.error or "")[:500]
    rows = await activity(app_sessions, org.org_id, bud.id)
    assert activity_types(rows) == ["skill_invoked", "skill_failed"]
    assert rows[-1].message == job.error
    assert (await load_bud(app_sessions, org.org_id, bud.id)).requirements_md == "refunds pls"
    events = [e.event_type for e in await timeline(app_sessions, org.org_id, bud.id)]
    assert "ai_agent_completed" not in events


async def test_timeout_kills_the_agent_and_surfaces_the_timeout_code(
    stage_claude: FakeClaudeRunner, app_sessions: Factory, job_runtime: JobRuntime
) -> None:
    """A hung CLI is killed; the task fails with the 600 s stage deadline in the message."""
    org = await seed_agent_org(app_sessions)
    bud = await add_bud(app_sessions, org.org_id, status=BUDStatus.CLOSED)
    stage_claude.enqueue(AgentScript.timeout(ToolCall("get_bud_context", {"limit": 1})))

    run = await trigger_stage(app_sessions, org.org_id, bud.id, "closed")
    job = await job_runtime.wait(run.job_id)

    assert (job.state, job.error_code) == (JobState.FAILED, "timeout")
    assert "600 seconds" in (job.error or "")
    (agent_run,) = stage_runs(stage_claude)
    assert agent_run.killed is True
    assert [c.status_code for c in agent_run.tool_calls] == [200]
    task = await load_task(app_sessions, run.task_id)
    assert (task.status, task.error_message) == (AgentTaskStatus.FAILED, (job.error or "")[:500])


async def test_max_turns_fails_with_its_own_code(
    stage_claude: FakeClaudeRunner, app_sessions: Factory, job_runtime: JobRuntime
) -> None:
    """``error_max_turns`` is a failure even though the CLI exited 0."""
    org = await seed_agent_org(app_sessions)
    bud = await add_bud(app_sessions, org.org_id, status=BUDStatus.TESTING)
    stage_claude.enqueue(AgentScript.max_turns(ToolCall("get_bud_context", {"limit": 1})))

    run = await trigger_stage(app_sessions, org.org_id, bud.id, "testing")
    job = await job_runtime.wait(run.job_id)

    assert (job.state, job.error_code) == (JobState.FAILED, "max_turns")
    (agent_run,) = stage_runs(stage_claude)
    assert agent_run.flag("--max-turns") == "15"
    stored = await load_bud(app_sessions, org.org_id, bud.id)
    assert (stored.qa_automation_cases, stored.test_plan_md) == (None, None)


async def test_prompt_builder_error_fails_the_task_before_any_agent_runs(
    stage_claude: FakeClaudeRunner, app_sessions: Factory, job_runtime: JobRuntime
) -> None:
    """Code review with no confirmed repos raises in the builder; no CLI is spawned."""
    org = await seed_agent_org(app_sessions)
    bud = await add_bud(app_sessions, org.org_id, status=BUDStatus.CODE_REVIEW)

    run = await trigger_stage(app_sessions, org.org_id, bud.id, "code_review")
    job = await job_runtime.wait(run.job_id)

    assert job.state == JobState.FAILED
    assert job.error == "No confirmed repos with commits for code review"
    assert stage_claude.runs == []
    task = await load_task(app_sessions, run.task_id)
    assert (task.status, task.error_message) == (AgentTaskStatus.FAILED, (job.error or "")[:500])
    rows = await activity(app_sessions, org.org_id, bud.id)
    assert activity_types(rows) == ["skill_failed"]


async def test_failed_task_frees_the_bud_for_a_new_run(
    stage_claude: FakeClaudeRunner, app_sessions: Factory, job_runtime: JobRuntime
) -> None:
    """After a crash the BUD has no active task, so the stage can be triggered again."""
    org = await seed_agent_org(app_sessions)
    bud = await add_bud(app_sessions, org.org_id, status=BUDStatus.CLOSED)
    stage_claude.enqueue(AgentScript.crash(), AgentScript.ok("# Recap\n\nShipped."))

    first = await trigger_stage(app_sessions, org.org_id, bud.id, "closed")
    await job_runtime.wait(first.job_id)
    second = await trigger_stage(app_sessions, org.org_id, bud.id, "closed")
    job = await job_runtime.wait(second.job_id)

    assert job.state == JobState.COMPLETED
    assert (await load_task(app_sessions, first.task_id)).status == AgentTaskStatus.FAILED
    assert (await load_task(app_sessions, second.task_id)).status == AgentTaskStatus.COMPLETED
