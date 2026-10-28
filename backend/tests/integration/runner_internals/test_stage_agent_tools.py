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

"""Stage agents whose MCP tool calls are refused: by the tool, or before the backend."""

from __future__ import annotations

import pytest

from app.models.bud import BUDStatus
from tests.fakes.claude_runner import FakeClaudeRunner
from tests.fakes.claude_script import AgentScript, ToolCall
from tests.fakes.git_repo import LocalGitRepo
from tests.fakes.seed import Factory, seed_repo
from tests.integration.runner_internals.output_support import TECH_SPEC, tech_arch_output
from tests.integration.runner_internals.runtime_support import JobRuntime
from tests.integration.runner_internals.stage_support import (
    add_bud,
    load_bud,
    seed_agent_org,
    trigger_stage,
)

pytestmark = pytest.mark.integration


async def test_write_bud_refused_by_the_tool_keeps_the_body(
    stage_claude: FakeClaudeRunner, app_sessions: Factory, job_runtime: JobRuntime
) -> None:
    """``write_bud`` without a title answers an error; the body is not clobbered."""
    org = await seed_agent_org(app_sessions)
    bud = await add_bud(app_sessions, org.org_id, requirements_md="refunds pls")
    bad = {"bud_number": bud.bud_number, "requirements_md": "half a doc"}
    stage_claude.enqueue(AgentScript.ok("Saved.", ToolCall("write_bud", bad)))

    run = await trigger_stage(app_sessions, org.org_id, bud.id, "bud")
    await job_runtime.wait(run.job_id)

    (call,) = stage_claude.tool_calls("write_bud")
    assert (call.status_code, call.is_error) == (200, True)
    assert call.response == {"success": False, "error": "`title` is required"}
    assert (await load_bud(app_sessions, org.org_id, bud.id)).requirements_md == "refunds pls"


async def test_tool_outside_the_skill_list_is_refused_before_the_backend(
    stage_claude: FakeClaudeRunner, app_sessions: Factory, job_runtime: JobRuntime
) -> None:
    """The PM skill does not expose ``write_bud_design``; the call never leaves the CLI."""
    org = await seed_agent_org(app_sessions)
    bud = await add_bud(app_sessions, org.org_id)
    design = {"bud_id": str(bud.id), "html": "<html></html>"}
    stage_claude.enqueue(AgentScript.ok("Done.", ToolCall("write_bud_design", design)))

    run = await trigger_stage(app_sessions, org.org_id, bud.id, "bud")
    await job_runtime.wait(run.job_id)

    (call,) = stage_claude.tool_calls("write_bud_design")
    assert (call.refused, call.status_code) == (True, None)
    assert call.response == {"error": "tool not exposed"}


async def test_internal_token_cannot_use_the_user_only_update_bud_tool(
    stage_claude: FakeClaudeRunner,
    app_sessions: Factory,
    job_runtime: JobRuntime,
    git_repo: LocalGitRepo,
) -> None:
    """The tech planner's ``update_bud`` needs a user token; the spec still lands."""
    org = await seed_agent_org(app_sessions)
    await seed_repo(app_sessions, org.org_id, git_repo)
    bud = await add_bud(app_sessions, org.org_id, status=BUDStatus.TECH_ARCH)
    update = {"bud_id": str(bud.id), "content": "# x", "expected_phase": "tech_arch"}
    stage_claude.enqueue(
        AgentScript.ok(tech_arch_output("shop-api"), ToolCall("update_bud", update))
    )

    run = await trigger_stage(app_sessions, org.org_id, bud.id, "tech_arch")
    await job_runtime.wait(run.job_id)

    (call,) = stage_claude.tool_calls("update_bud")
    assert call.is_error is True
    assert call.response["code"] == "user_token_required"
    assert (await load_bud(app_sessions, org.org_id, bud.id)).tech_spec_md == TECH_SPEC
