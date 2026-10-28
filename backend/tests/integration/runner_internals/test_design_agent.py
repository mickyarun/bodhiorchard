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

"""The design stage: ``POST /designs/generate`` → design job → scripted designer.

The designer persists through ``write_bud_design``; the job checks the row,
not the reply. Each spawn is held until the request has committed its rows,
as the real CLI's start-up time does in production.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import pytest
from httpx import AsyncClient

from app.models.bud import BUDDesignStatus, BUDStatus
from app.models.bud_agent_task import AgentTaskStatus
from app.schemas.jobs import JobState
from tests.fakes.claude_runner import FakeClaudeRunner
from tests.fakes.claude_script import AgentScript, ToolCall
from tests.fakes.git_repo import LocalGitRepo
from tests.fakes.seed import Factory, auth_headers, seed_repo
from tests.integration.runner_internals.output_support import add_design_system, load_design
from tests.integration.runner_internals.runtime_support import JobRuntime, SpawnGate
from tests.integration.runner_internals.stage_support import (
    activity,
    activity_types,
    add_bud,
    load_task,
    seed_agent_org,
    timeline,
)

pytestmark = pytest.mark.integration

WIREFRAME = "<!DOCTYPE html><html><body><h1>Refund</h1><button>Refund</button></body></html>"


@dataclass(frozen=True)
class DesignRun:
    """One generate request: the ids it returned."""

    org_id: uuid.UUID
    bud_id: uuid.UUID
    repo_id: uuid.UUID
    design_id: uuid.UUID
    job_id: str


async def _generate(client: AsyncClient, factory: Factory, git_repo: LocalGitRepo) -> DesignRun:
    """Seed a design-phase BUD with a design system and request generation."""
    org = await seed_agent_org(factory)
    repo_id = await seed_repo(factory, org.org_id, git_repo)
    await add_design_system(factory, org.org_id, repo_id)
    bud = await add_bud(factory, org.org_id, status=BUDStatus.DESIGN)
    response = await client.post(
        f"/api/v1/buds/{bud.id}/designs/generate",
        json={"repo_ids": [str(repo_id)]},
        headers=auth_headers(org.owner_id, org.org_id),
    )
    assert response.status_code == 202, response.text
    (row,) = response.json()
    return DesignRun(org.org_id, bud.id, repo_id, uuid.UUID(row["designId"]), row["jobId"])


def _write(run: DesignRun, *, bud_id: uuid.UUID | None = None, html: str = WIREFRAME) -> ToolCall:
    """The designer's ``write_bud_design`` call for ``run``."""
    params = {
        "bud_id": str(bud_id or run.bud_id),
        "repo_id": str(run.repo_id),
        "design_id": str(run.design_id),
        "html": html,
    }
    return ToolCall("write_bud_design", params)


async def test_designer_write_marks_the_design_ready_and_completes_the_task(
    stage_claude: FakeClaudeRunner,
    client: AsyncClient,
    app_sessions: Factory,
    job_runtime: JobRuntime,
    git_repo: LocalGitRepo,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A scripted ``write_bud_design`` lands READY HTML and a ``design_generated`` event."""
    gate = SpawnGate(stage_claude, monkeypatch)
    run = await _generate(client, app_sessions, git_repo)
    stage_claude.enqueue(
        AgentScript.ok(
            '{"reply": "Wireframe saved."}',
            ToolCall("get_design_system", {"repo_id": str(run.repo_id)}),
            _write(run),
        )
    )
    gate.release()

    job = await job_runtime.wait(run.job_id)

    assert job.state == JobState.COMPLETED
    assert job.result == {"reply": "Wireframe saved.", "design_id": str(run.design_id)}
    design = await load_design(app_sessions, run.org_id, run.design_id)
    assert design.status == BUDDesignStatus.READY
    assert "<button>Refund</button>" in (design.design_html or "")
    (designer_run, *_estimates) = stage_claude.runs
    assert designer_run.mcp_tools == [
        "list_design_systems",
        "get_design_system",
        "get_bud_designs",
        "write_bud_design",
    ]
    events = await timeline(app_sessions, run.org_id, run.bud_id)
    (generated,) = [e for e in events if e.event_type == "design_generated"]
    assert generated.detail == {"design_id": str(run.design_id), "repo_id": str(run.repo_id)}
    rows = await activity(app_sessions, run.org_id, run.bud_id)
    assert activity_types(rows) == ["skill_invoked", "skill_completed"]
    task_id = rows[0].task_id
    assert task_id is not None
    assert (await load_task(app_sessions, task_id)).status == AgentTaskStatus.COMPLETED


async def test_designer_that_never_writes_fails_the_design_and_the_job(
    stage_claude: FakeClaudeRunner,
    client: AsyncClient,
    app_sessions: Factory,
    job_runtime: JobRuntime,
    git_repo: LocalGitRepo,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No tool call and no complete document in the reply: nothing is saved."""
    gate = SpawnGate(stage_claude, monkeypatch)
    run = await _generate(client, app_sessions, git_repo)
    stage_claude.enqueue(AgentScript.ok("I would put a <html> refund button here."))
    gate.release()

    job = await job_runtime.wait(run.job_id)

    assert (job.state, job.error) == (JobState.FAILED, "Agent did not call write_bud_design MCP")
    design = await load_design(app_sessions, run.org_id, run.design_id)
    assert design.status == BUDDesignStatus.FAILED
    rows = await activity(app_sessions, run.org_id, run.bud_id)
    assert activity_types(rows) == ["skill_invoked", "skill_failed"]
    task_id = rows[0].task_id
    assert task_id is not None
    task = await load_task(app_sessions, task_id)
    assert (task.status, task.error_message) == ("failed", "Design generation failed")
    events = [e.event_type for e in await timeline(app_sessions, run.org_id, run.bud_id)]
    assert "ai_agent_failed" in events


@pytest.mark.xfail(
    strict=True,
    reason=(
        "the output fallback reads 'success' but write_bud_design answers 'saved', "
        "so a recovered wireframe is reported failed; fixed by branch fix/design-fallback-saved"
    ),
)
async def test_designer_reply_with_a_whole_document_is_saved_without_the_tool(
    stage_claude: FakeClaudeRunner,
    client: AsyncClient,
    app_sessions: Factory,
    job_runtime: JobRuntime,
    git_repo: LocalGitRepo,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The output fallback stores a complete fenced document as if the tool had run."""
    gate = SpawnGate(stage_claude, monkeypatch)
    run = await _generate(client, app_sessions, git_repo)
    stage_claude.enqueue(
        AgentScript.ok(f"Here it is:\n\n```html\n{WIREFRAME}\n```").with_insight()
    )
    gate.release()

    job = await job_runtime.wait(run.job_id)

    assert job.state == JobState.COMPLETED
    design = await load_design(app_sessions, run.org_id, run.design_id)
    assert design.status == BUDDesignStatus.READY
    assert "Insight" not in (design.design_html or "")


async def test_write_rejected_by_the_tool_leaves_the_design_failed(
    stage_claude: FakeClaudeRunner,
    client: AsyncClient,
    app_sessions: Factory,
    job_runtime: JobRuntime,
    git_repo: LocalGitRepo,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``write_bud_design`` naming another BUD answers an error; the row is not written."""
    gate = SpawnGate(stage_claude, monkeypatch)
    run = await _generate(client, app_sessions, git_repo)
    stage_claude.enqueue(AgentScript.ok("Saved.", _write(run, bud_id=uuid.uuid4())))
    gate.release()

    job = await job_runtime.wait(run.job_id)

    (call,) = stage_claude.tool_calls("write_bud_design")
    assert call.is_error is True
    assert call.response["success"] is False
    assert job.state == JobState.FAILED
    design = await load_design(app_sessions, run.org_id, run.design_id)
    assert (design.status, design.design_html) == (BUDDesignStatus.FAILED, None)
