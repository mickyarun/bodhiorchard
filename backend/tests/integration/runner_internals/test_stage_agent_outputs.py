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

"""Result handlers fed the messy outputs a real agent produces.

The run itself succeeds in every case here; what is pinned is what the
result handler makes of the text (or the tool calls) it was given.
"""

from __future__ import annotations

import pytest

from app.models.bud import BUDStatus
from app.models.bud_agent_task import AgentTaskStatus
from app.schemas.jobs import JobState
from tests.fakes.claude_runner import FakeClaudeRunner
from tests.fakes.claude_script import AgentScript
from tests.fakes.git_repo import LocalGitRepo
from tests.fakes.seed import Factory, seed_repo
from tests.integration.runner_internals.output_support import (
    TECH_SPEC,
    learning,
    tech_arch_output,
    versions,
)
from tests.integration.runner_internals.runtime_support import JobRuntime
from tests.integration.runner_internals.stage_support import (
    add_bud,
    load_bud,
    load_task,
    seed_agent_org,
    set_org_config,
    timeline,
    trigger_stage,
)

pytestmark = pytest.mark.integration


async def test_insight_and_chat_preamble_are_stripped_from_the_tech_spec(
    stage_claude: FakeClaudeRunner,
    app_sessions: Factory,
    job_runtime: JobRuntime,
    git_repo: LocalGitRepo,
) -> None:
    """The stored spec starts at its own ``# `` heading."""
    org = await seed_agent_org(app_sessions)
    await seed_repo(app_sessions, org.org_id, git_repo)
    bud = await add_bud(app_sessions, org.org_id, status=BUDStatus.TECH_ARCH)
    stage_claude.enqueue(
        AgentScript.ok(tech_arch_output("shop-api")).with_preamble().with_insight()
    )

    run = await trigger_stage(app_sessions, org.org_id, bud.id, "tech_arch")
    await job_runtime.wait(run.job_id)

    assert (await load_bud(app_sessions, org.org_id, bud.id)).tech_spec_md == TECH_SPEC


async def test_empty_tech_spec_output_fails_and_keeps_the_current_spec(
    stage_claude: FakeClaudeRunner, app_sessions: Factory, job_runtime: JobRuntime
) -> None:
    """An empty answer is a failed run; the spec the BUD has stays."""
    org = await seed_agent_org(app_sessions)
    bud = await add_bud(
        app_sessions, org.org_id, status=BUDStatus.TECH_ARCH, tech_spec_md="# Old plan"
    )
    stage_claude.enqueue(AgentScript.ok(""))

    run = await trigger_stage(app_sessions, org.org_id, bud.id, "tech_arch")
    job = await job_runtime.wait(run.job_id)

    assert (await load_bud(app_sessions, org.org_id, bud.id)).tech_spec_md == "# Old plan"
    assert job.state == JobState.FAILED
    assert "no tech spec" in (job.error or "")
    assert (await load_task(app_sessions, run.task_id)).status == AgentTaskStatus.FAILED


async def test_empty_learning_output_writes_no_recap(
    stage_claude: FakeClaudeRunner, app_sessions: Factory, job_runtime: JobRuntime
) -> None:
    """A blank (insight-only) recap completes the task but records nothing."""
    org = await seed_agent_org(app_sessions)
    bud = await add_bud(app_sessions, org.org_id, status=BUDStatus.CLOSED)
    stage_claude.enqueue(AgentScript.ok("").with_insight())

    run = await trigger_stage(app_sessions, org.org_id, bud.id, "closed")
    await job_runtime.wait(run.job_id)

    task = await load_task(app_sessions, run.task_id)
    assert task.status == AgentTaskStatus.COMPLETED
    assert task.result_summary == {"section": "retrospective_md", "output_length": 0}
    assert await learning(app_sessions, org.org_id, bud.id) is None
    events = [e.event_type for e in await timeline(app_sessions, org.org_id, bud.id)]
    assert "learning_recorded" not in events


async def test_malformed_testing_json_fails_and_keeps_the_recorded_cases(
    stage_claude: FakeClaudeRunner, app_sessions: Factory, job_runtime: JobRuntime
) -> None:
    """Unparseable test cases are a failed run; tester results and evidence stay."""
    org = await seed_agent_org(app_sessions)
    recorded = [{"id": "TC-OLD", "result": "passed", "evidence": ["shot.png"]}]
    bud = await add_bud(
        app_sessions, org.org_id, status=BUDStatus.TESTING, qa_manual_cases=recorded
    )
    stage_claude.enqueue(AgentScript.ok('Here are the cases: {"automation_test_cases": [oops'))

    run = await trigger_stage(app_sessions, org.org_id, bud.id, "testing")
    job = await job_runtime.wait(run.job_id)

    assert (await load_bud(app_sessions, org.org_id, bud.id)).qa_manual_cases == recorded
    assert job.state == JobState.FAILED
    assert (await load_task(app_sessions, run.task_id)).status == AgentTaskStatus.FAILED


async def test_automation_cases_are_dropped_when_the_org_turned_automation_off(
    stage_claude: FakeClaudeRunner, app_sessions: Factory, job_runtime: JobRuntime
) -> None:
    """The handler enforces ``qa.enabled = false`` even if the agent ignores it."""
    org = await seed_agent_org(app_sessions)
    await set_org_config(app_sessions, org.org_id, {"qa": {"enabled": False}})
    bud = await add_bud(app_sessions, org.org_id, status=BUDStatus.TESTING)
    stage_claude.enqueue(
        AgentScript.ok('{"automation_test_cases": [{"id": "TC-001"}], "manual_test_cases": []}')
    )

    run = await trigger_stage(app_sessions, org.org_id, bud.id, "testing")
    await job_runtime.wait(run.job_id)

    assert (await load_bud(app_sessions, org.org_id, bud.id)).qa_automation_cases == []


async def test_requirements_agent_that_never_writes_leaves_the_body_alone(
    stage_claude: FakeClaudeRunner, app_sessions: Factory, job_runtime: JobRuntime
) -> None:
    """No ``write_bud`` call on a BUD that has a body: it completes, nothing changes."""
    org = await seed_agent_org(app_sessions)
    bud = await add_bud(app_sessions, org.org_id, requirements_md="refunds pls")
    stage_claude.enqueue(AgentScript.ok("I refined the requirements."))

    run = await trigger_stage(app_sessions, org.org_id, bud.id, "bud")
    await job_runtime.wait(run.job_id)

    assert (await load_bud(app_sessions, org.org_id, bud.id)).requirements_md == "refunds pls"
    assert (await load_task(app_sessions, run.task_id)).status == AgentTaskStatus.COMPLETED
    assert await versions(app_sessions, bud.id) == []
