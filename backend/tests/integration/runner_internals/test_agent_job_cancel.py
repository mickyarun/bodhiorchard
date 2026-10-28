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

"""Cancelling real agent jobs over HTTP while the worker owns them."""

from __future__ import annotations

import asyncio

import pytest
from httpx import AsyncClient

from app.models.bud import BUDStatus
from app.models.bud_agent_task import AgentTaskStatus
from app.models.user import User
from app.schemas.jobs import JobState
from app.services import job_queue
from tests.fakes.claude_runner import FakeClaudeRunner
from tests.fakes.claude_script import AgentScript, ToolCall
from tests.fakes.seed import Factory, auth_headers
from tests.integration.runner_internals.output_support import stage_runs
from tests.integration.runner_internals.runtime_support import JobRuntime, SpawnGate
from tests.integration.runner_internals.stage_support import (
    activity,
    activity_types,
    add_bud,
    load_task,
    seed_agent_org,
    trigger_stage,
)

pytestmark = pytest.mark.integration


async def test_cancel_route_stops_a_running_job_and_the_worker_carries_on(
    stage_claude: FakeClaudeRunner,
    client: AsyncClient,
    app_sessions: Factory,
    job_runtime: JobRuntime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``POST /jobs/{id}/cancel`` mid-run: CANCELLED job, FAILED task, next job runs."""
    gate = SpawnGate(stage_claude, monkeypatch)
    org = await seed_agent_org(app_sessions)
    headers = auth_headers(org.owner_id, org.org_id)
    first = await add_bud(app_sessions, org.org_id, status=BUDStatus.CLOSED)
    second = await add_bud(app_sessions, org.org_id, status=BUDStatus.CLOSED)
    stage_claude.enqueue(AgentScript.ok("# Second recap"))

    run = await trigger_stage(app_sessions, org.org_id, first.id, "closed")
    await gate.wait_entered()
    response = await client.post(f"/api/v1/jobs/{run.job_id}/cancel", headers=headers)
    job = await job_runtime.wait(run.job_id)
    gate.release()
    later = await trigger_stage(app_sessions, org.org_id, second.id, "closed")
    later_job = await job_runtime.wait(later.job_id)

    assert response.status_code == 200
    reason = response.json()["statusMessage"]
    async with app_sessions() as db:
        owner = await db.get(User, org.owner_id)
    assert owner is not None
    assert reason == f"Cancelled by {owner.email}"
    assert (job.state, job.error, job.status_message) == (JobState.CANCELLED, reason, "Cancelled")
    task = await load_task(app_sessions, run.task_id)
    assert (task.status, task.error_message) == (AgentTaskStatus.FAILED, reason)
    rows = await activity(app_sessions, org.org_id, first.id)
    assert activity_types(rows) == ["skill_invoked", "skill_failed"]
    assert rows[-1].message == reason
    assert later_job.state == JobState.COMPLETED
    assert len(stage_runs(stage_claude)) == 1


async def test_cancel_while_the_agent_hangs_kills_the_cli(
    stage_claude: FakeClaudeRunner,
    client: AsyncClient,
    app_sessions: Factory,
    job_runtime: JobRuntime,
) -> None:
    """Cancelling a job whose CLI never answers kills that process, not just the task."""
    org = await seed_agent_org(app_sessions)
    bud = await add_bud(app_sessions, org.org_id, status=BUDStatus.CLOSED)
    stage_claude.enqueue(AgentScript.timeout(ToolCall("get_bud_context", {"limit": 1})))
    run = await trigger_stage(app_sessions, org.org_id, bud.id, "closed")

    async def _spawned() -> None:
        while not stage_runs(stage_claude):
            await asyncio.sleep(0.01)
        await asyncio.sleep(0.05)

    await asyncio.wait_for(_spawned(), 5)
    response = await client.post(
        f"/api/v1/jobs/{run.job_id}/cancel", headers=auth_headers(org.owner_id, org.org_id)
    )
    job = await job_runtime.wait(run.job_id)

    assert response.status_code == 200
    assert job.state == JobState.CANCELLED
    (agent_run,) = stage_runs(stage_claude)
    assert agent_run.killed is True
    assert [c.status_code for c in agent_run.tool_calls] == [200]
    assert (await load_task(app_sessions, run.task_id)).status == AgentTaskStatus.FAILED


async def test_task_cancelled_while_queued_never_runs(
    stage_claude: FakeClaudeRunner,
    client: AsyncClient,
    app_sessions: Factory,
    job_runtime: JobRuntime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The task cancel route drops a real agent job still waiting behind another.

    The queue-level behaviour is pinned on main by
    ``tests/integration/test_agent_cancel_queued_job.py`` with a stand-in
    handler; this drives it through the HTTP route and the real agent handler.
    """
    gate = SpawnGate(stage_claude, monkeypatch)
    org = await seed_agent_org(app_sessions)
    busy = await add_bud(app_sessions, org.org_id, status=BUDStatus.CLOSED)
    waiting = await add_bud(app_sessions, org.org_id, status=BUDStatus.CLOSED)
    stage_claude.default = AgentScript.ok("# Recap")

    held = await trigger_stage(app_sessions, org.org_id, busy.id, "closed")
    await gate.wait_entered()
    queued = await trigger_stage(app_sessions, org.org_id, waiting.id, "closed")
    response = await client.post(
        f"/api/v1/buds/{waiting.id}/agent-tasks/{queued.task_id}/cancel",
        headers=auth_headers(org.owner_id, org.org_id),
    )
    gate.release()
    await job_runtime.wait(held.job_id)
    _, _, queue = job_queue._registry[job_queue.JOB_BUD_AGENT]
    await asyncio.wait_for(queue.join(), 5)

    assert (response.status_code, response.json()["status"]) == (202, AgentTaskStatus.FAILED)
    assert (await load_task(app_sessions, queued.task_id)).status == AgentTaskStatus.FAILED
    assert len(stage_runs(stage_claude)) == 1
