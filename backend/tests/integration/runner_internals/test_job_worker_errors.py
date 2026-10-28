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

"""Agent jobs the worker must refuse or survive: bad payloads and failing handlers."""

from __future__ import annotations

import uuid

import pytest

from app.models.bud import BUDStatus
from app.schemas.jobs import BUDAgentTaskPayload, JobState
from app.services import job_queue
from tests.fakes.claude_runner import FakeClaudeRunner
from tests.fakes.claude_script import AgentScript
from tests.fakes.seed import Factory
from tests.integration.runner_internals.output_support import stage_runs
from tests.integration.runner_internals.runtime_support import JobRuntime
from tests.integration.runner_internals.stage_support import (
    add_bud,
    load_task,
    seed_agent_org,
    trigger_stage,
)

pytestmark = pytest.mark.integration


async def test_missing_task_row_fails_the_job_without_running_an_agent(
    stage_claude: FakeClaudeRunner, app_sessions: Factory, job_runtime: JobRuntime
) -> None:
    """A payload naming no task row: FAILED, and nothing is spawned."""
    org = await seed_agent_org(app_sessions)
    bud = await add_bud(app_sessions, org.org_id)
    payload = BUDAgentTaskPayload(
        org_id=str(org.org_id), bud_id=str(bud.id), task_id=str(uuid.uuid4())
    )

    job = job_queue.create_job(job_queue.JOB_BUD_AGENT, payload=payload.model_dump())
    done = await job_runtime.wait(job.job_id)

    assert (done.state, done.error) == (JobState.FAILED, "Agent task not found")
    assert stage_claude.runs == []


async def test_task_of_another_org_is_refused_and_left_untouched(
    stage_claude: FakeClaudeRunner, app_sessions: Factory, job_runtime: JobRuntime
) -> None:
    """A payload whose org does not own the task row fails as ``Org mismatch``."""
    owner = await seed_agent_org(app_sessions)
    intruder = await seed_agent_org(app_sessions)
    bud = await add_bud(app_sessions, owner.org_id, status=BUDStatus.CLOSED)
    stage_claude.enqueue(AgentScript.ok("# Recap"))
    run = await trigger_stage(app_sessions, owner.org_id, bud.id, "closed")
    await job_runtime.wait(run.job_id)
    before = await load_task(app_sessions, run.task_id)
    payload = BUDAgentTaskPayload(
        org_id=str(intruder.org_id), bud_id=str(bud.id), task_id=str(run.task_id)
    )

    forged = job_queue.create_job(job_queue.JOB_BUD_AGENT, payload=payload.model_dump())
    done = await job_runtime.wait(forged.job_id)

    assert (done.state, done.error) == (JobState.FAILED, "Org mismatch")
    after = await load_task(app_sessions, run.task_id)
    assert (after.status, after.result_summary) == (before.status, before.result_summary)
    assert len(stage_runs(stage_claude)) == 1


async def test_worker_survives_a_handler_that_raises(job_runtime: JobRuntime) -> None:
    """A malformed triage payload raises in the handler; the next job still runs."""
    broken = job_queue.create_job(job_queue.JOB_TRIAGE, payload={"team_id": "T1"})
    unknown_team = job_queue.create_job(
        job_queue.JOB_TRIAGE,
        payload={
            "team_id": f"T-{uuid.uuid4().hex[:8]}",
            "action": "start_triage",
            "event_type": "reaction_added",
            "event_data": {"item": {"channel": "C1", "ts": "1.0"}},
        },
    )

    first = await job_runtime.wait(broken.job_id)
    second = await job_runtime.wait(unknown_team.job_id)

    assert (first.state, first.status_message) == (JobState.FAILED, "Failed")
    assert "validation error" in (first.error or "")
    assert second.state == JobState.FAILED
    assert (second.error or "").startswith("Organization not found for team T-")
