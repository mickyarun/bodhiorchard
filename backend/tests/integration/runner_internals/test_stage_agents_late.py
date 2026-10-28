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

"""The later BUD stage agents end to end: testing cases and the learning recap."""

from __future__ import annotations

import pytest

from app.models.bud import BUDStatus
from tests.fakes.app_state import EventRecorder
from tests.fakes.claude_runner import FakeClaudeRunner
from tests.fakes.claude_script import AgentScript
from tests.fakes.seed import Factory
from tests.integration.runner_internals.output_support import (
    learning,
    qa_output,
)
from tests.integration.runner_internals.runtime_support import JobRuntime
from tests.integration.runner_internals.stage_support import (
    add_bud,
    load_bud,
    load_task,
    seed_agent_org,
    timeline,
    trigger_stage,
)

pytestmark = pytest.mark.integration


async def test_testing_stores_cases_and_fills_manual_defaults(
    stage_claude: FakeClaudeRunner, app_sessions: Factory, job_runtime: JobRuntime
) -> None:
    """The testing JSON lands in the QA columns; manual cases start ``pending``."""
    org = await seed_agent_org(app_sessions)
    bud = await add_bud(app_sessions, org.org_id, status=BUDStatus.TESTING)
    stage_claude.enqueue(AgentScript.ok(qa_output(automation=2, manual=1)))

    run = await trigger_stage(app_sessions, org.org_id, bud.id, "testing")
    await job_runtime.wait(run.job_id)

    stored = await load_bud(app_sessions, org.org_id, bud.id)
    assert [c["id"] for c in stored.qa_automation_cases or []] == ["TC-001", "TC-002"]
    (manual,) = stored.qa_manual_cases or []
    assert (manual["result"], manual["evidence"], manual["tester_name"]) == ("pending", [], None)
    assert stored.qa_execution_plan_md == "Run unit tests, then manual checks."
    assert stored.test_plan_md is not None
    assert "**2** automation test cases" in stored.test_plan_md
    summary = (await load_task(app_sessions, run.task_id)).result_summary
    assert summary == {"section": "qa_execution_plan_md", "automation_count": 2, "manual_count": 1}


async def test_learning_recap_is_stored_without_insight_and_announced(
    stage_claude: FakeClaudeRunner,
    app_sessions: Factory,
    job_runtime: JobRuntime,
    event_recorder: EventRecorder,
) -> None:
    """The closed-stage recap lands on the learning row with a timeline event."""
    org = await seed_agent_org(app_sessions)
    bud = await add_bud(app_sessions, org.org_id, status=BUDStatus.CLOSED)
    recap = "# What we learned\n\nRefunds shipped two days late."
    stage_claude.enqueue(AgentScript.ok(recap).with_insight())

    run = await trigger_stage(app_sessions, org.org_id, bud.id, "closed")
    await job_runtime.wait(run.job_id)
    await event_recorder.settle()

    row = await learning(app_sessions, org.org_id, bud.id)
    assert row is not None
    assert row.retrospective_md == recap
    assert row.embedding is not None
    events = await timeline(app_sessions, org.org_id, bud.id)
    (recorded,) = [e for e in events if e.event_type == "learning_recorded"]
    assert recorded.detail == {"char_count": len(recap), "task_id": str(run.task_id)}
    assert event_recorder.payloads(f"bud:{bud.id}:activity")[-1]["char_count"] == len(recap)
