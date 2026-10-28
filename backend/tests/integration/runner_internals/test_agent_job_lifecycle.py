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

"""A real agent job through the queue: progress events, the status route, notifications."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.models.bud import BUDStatus
from app.models.bud_agent_task import AgentTaskStatus
from tests.fakes.app_state import EventRecorder
from tests.fakes.claude_runner import FakeClaudeRunner
from tests.fakes.claude_script import AgentScript, ToolCall
from tests.fakes.seed import Factory, auth_headers
from tests.integration.runner_internals.output_support import notifications
from tests.integration.runner_internals.runtime_support import (
    JobRuntime,
    SpawnGate,
    wait_for_event,
)
from tests.integration.runner_internals.stage_support import (
    add_bud,
    load_task,
    seed_agent_org,
    trigger_stage,
)

pytestmark = pytest.mark.integration


async def test_progress_is_published_on_the_job_topic_in_order(
    stage_claude: FakeClaudeRunner,
    app_sessions: Factory,
    job_runtime: JobRuntime,
    event_recorder: EventRecorder,
) -> None:
    """Each phase of the handler and each tool call reaches ``job:{id}``."""
    org = await seed_agent_org(app_sessions)
    bud = await add_bud(app_sessions, org.org_id, status=BUDStatus.CLOSED)
    stage_claude.enqueue(AgentScript.ok("# Recap", ToolCall("get_bud_context", {"limit": 1})))

    run = await trigger_stage(app_sessions, org.org_id, bud.id, "closed")
    await job_runtime.wait(run.job_id)
    await event_recorder.settle()

    frames = event_recorder.payloads(f"job:{run.job_id}")
    steps = [(f["state"], f["statusMessage"], f["progressPct"]) for f in frames]
    assert steps == [
        ("running", "Starting...", 0),
        ("running", "Loading task...", 5),
        ("running", "Building prompt...", 10),
        ("running", "Running agent...", 20),
        ("running", "Reading BUD requirements...", 20),
        ("running", "Saving results...", 90),
        ("completed", "Done", 100),
    ]
    activity_frames = event_recorder.payloads(f"agent_activity:{org.org_id}")
    kinds = [f["event_type"] for f in activity_frames]
    assert kinds == ["skill_invoked", "skill_completed", "skill_completed"]
    assert activity_frames[-1]["task_id"] == str(run.task_id)


async def test_status_route_shows_the_running_job_then_its_result(
    stage_claude: FakeClaudeRunner,
    client: AsyncClient,
    app_sessions: Factory,
    job_runtime: JobRuntime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``GET /api/v1/jobs/{id}/status`` mirrors the in-memory job while it runs."""
    gate = SpawnGate(stage_claude, monkeypatch)
    org = await seed_agent_org(app_sessions)
    headers = auth_headers(org.owner_id, org.org_id)
    bud = await add_bud(app_sessions, org.org_id, status=BUDStatus.CLOSED)
    stage_claude.enqueue(AgentScript.ok("# Recap"))

    run = await trigger_stage(app_sessions, org.org_id, bud.id, "closed")
    await gate.wait_entered()
    running = await client.get(f"/api/v1/jobs/{run.job_id}/status", headers=headers)
    assert (await load_task(app_sessions, run.task_id)).status == AgentTaskStatus.RUNNING
    gate.release()
    await job_runtime.wait(run.job_id)
    done = await client.get(f"/api/v1/jobs/{run.job_id}/status", headers=headers)

    assert running.status_code == 200
    body = running.json()
    assert (body["jobType"], body["state"], body["statusMessage"]) == (
        "bud_agent",
        "running",
        "Running agent...",
    )
    assert (done.json()["state"], done.json()["progressPct"]) == ("completed", 100)
    unknown = await client.get(f"/api/v1/jobs/{uuid.uuid4()}/status", headers=headers)
    assert unknown.status_code == 404
    anonymous = await client.get(f"/api/v1/jobs/{run.job_id}/status")
    assert anonymous.status_code == 401


@pytest.mark.parametrize(
    ("script", "kind", "title"),
    [
        (AgentScript.ok("# Recap"), "job_completed", "BUD Agent completed"),
        (AgentScript.crash(stderr="boom"), "job_failed", "BUD Agent failed"),
    ],
)
async def test_terminal_job_notifies_the_user_who_triggered_it(
    stage_claude: FakeClaudeRunner,
    app_sessions: Factory,
    job_runtime: JobRuntime,
    event_recorder: EventRecorder,
    script: AgentScript,
    kind: str,
    title: str,
) -> None:
    """A finished or failed run leaves an in-app notification for its trigger."""
    org = await seed_agent_org(app_sessions)
    bud = await add_bud(app_sessions, org.org_id, status=BUDStatus.CLOSED)
    stage_claude.enqueue(script)

    run = await trigger_stage(
        app_sessions, org.org_id, bud.id, "closed", triggered_by=org.owner_id
    )
    await job_runtime.wait(run.job_id)
    await wait_for_event(event_recorder, f"notifications:{org.owner_id}")

    (note,) = await notifications(app_sessions, org.owner_id)
    assert (note.type, note.title, note.job_id) == (kind, title, run.job_id)
    assert note.org_id == org.org_id
    if kind == "job_failed":
        assert "boom" in (note.message or "")
