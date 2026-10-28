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

"""Retrying a failed agent task over HTTP, with a real agent job behind it.

The request session's commits are slowed (``slow_commit_support``), so a
route that queues the job before committing the new attempt loses the race
to the worker every time, as it does under real database latency.
"""

from __future__ import annotations

import uuid

import pytest

from app.models.bud import BUDStatus
from app.models.bud_agent_task import AgentTaskStatus
from app.schemas.jobs import JobState
from tests.fakes.claude_runner import FakeClaudeRunner
from tests.fakes.claude_script import AgentScript
from tests.fakes.seed import Factory, auth_headers
from tests.integration.runner_internals.output_support import stage_runs
from tests.integration.runner_internals.runtime_support import JobRuntime
from tests.integration.runner_internals.slow_commit_support import slow_commit_client
from tests.integration.runner_internals.stage_support import (
    add_bud,
    load_task,
    seed_agent_org,
    trigger_stage,
)

pytestmark = pytest.mark.integration


@pytest.mark.xfail(
    strict=True,
    reason=(
        "the retry route queues the job before committing the new task row, so the "
        "worker finds no task; fixed by branch fix/agent-retry-commit-before-enqueue"
    ),
)
async def test_retry_route_runs_a_failed_task_as_a_new_attempt(
    stage_claude: FakeClaudeRunner, app_sessions: Factory, job_runtime: JobRuntime
) -> None:
    """A crashed task retried over HTTP becomes attempt 2 and completes."""
    org = await seed_agent_org(app_sessions)
    bud = await add_bud(app_sessions, org.org_id, status=BUDStatus.CLOSED)
    stage_claude.enqueue(AgentScript.crash(stderr="boom"), AgentScript.ok("# Recap"))
    run = await trigger_stage(app_sessions, org.org_id, bud.id, "closed")
    await job_runtime.wait(run.job_id)

    async with slow_commit_client(app_sessions) as client:
        response = await client.post(
            f"/api/v1/buds/{bud.id}/agent-tasks/{run.task_id}/retry",
            headers=auth_headers(org.owner_id, org.org_id),
        )
    body = response.json()
    retried = await job_runtime.wait(body["job_id"])

    assert (response.status_code, body["attempt"]) == (202, 2)
    assert retried.state == JobState.COMPLETED, retried.error
    assert len(stage_runs(stage_claude)) == 2
    new_task = await load_task(app_sessions, uuid.UUID(body["id"]))
    assert new_task.status == AgentTaskStatus.COMPLETED
    assert (await load_task(app_sessions, run.task_id)).status == AgentTaskStatus.FAILED


async def test_only_a_failed_task_can_be_retried(
    stage_claude: FakeClaudeRunner, app_sessions: Factory, job_runtime: JobRuntime
) -> None:
    """Retrying a completed task is refused and starts nothing."""
    org = await seed_agent_org(app_sessions)
    bud = await add_bud(app_sessions, org.org_id, status=BUDStatus.CLOSED)
    stage_claude.enqueue(AgentScript.ok("# Recap"))
    run = await trigger_stage(app_sessions, org.org_id, bud.id, "closed")
    await job_runtime.wait(run.job_id)

    async with slow_commit_client(app_sessions) as client:
        response = await client.post(
            f"/api/v1/buds/{bud.id}/agent-tasks/{run.task_id}/retry",
            headers=auth_headers(org.owner_id, org.org_id),
        )

    assert response.status_code == 409
    assert response.json()["detail"] == "Only failed tasks can be retried"
    assert len(stage_runs(stage_claude)) == 1
