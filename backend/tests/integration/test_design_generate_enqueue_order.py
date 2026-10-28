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

"""``POST /buds/{id}/designs/generate`` commits its rows before it queues the design jobs.

The design worker runs a stand-in handler that does what a fast real run
does: read the task, land the wireframe and finish the task. The request's
commits are slowed (see ``design_generate_support``) so any write the route
makes after queueing lands after the handler's.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from app.models.bud import BUDDesign, BUDDesignStatus
from app.models.bud_agent_task import AgentTaskStatus, BUDAgentTask
from tests.integration.design_generate_support import (
    Factory,
    design_bud,
    design_workers,
    slow_commit_client,
)

pytestmark = pytest.mark.integration


async def test_fast_design_job_keeps_its_ready_row_and_completed_task(
    pg_session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The job sees its rows, and its READY / COMPLETED writes survive the request."""
    seen: list[bool] = []
    task_ids: list[uuid.UUID] = []

    async def finish_design(job_id: str, payload: dict[str, Any]) -> None:
        async with pg_session_factory() as db:
            design = await db.get(BUDDesign, uuid.UUID(payload["design_id"]))
            task_ids.append(uuid.UUID(payload["task_id"]))
            task = await db.get(BUDAgentTask, task_ids[-1])
            seen.append(design is not None and task is not None)
            if design is None or task is None:
                raise LookupError("design rows are not visible to the worker")
            design.status = BUDDesignStatus.READY
            design.design_html = "<html></html>"
            task.status = AgentTaskStatus.COMPLETED
            await db.commit()

    bud = await design_bud(pg_session_factory)
    async with (
        design_workers(monkeypatch, finish_design),
        slow_commit_client(pg_session_factory) as client,
    ):
        response = await client.post(
            f"/api/v1/buds/{bud.bud_id}/designs/generate",
            json={"repo_ids": [str(bud.repo_id)]},
            headers=bud.headers,
        )

    assert response.status_code == 202, response.text
    (row,) = response.json()
    assert seen == [True]
    async with pg_session_factory() as db:
        design = await db.get(BUDDesign, uuid.UUID(row["designId"]))
        assert design is not None
        task = await db.get(BUDAgentTask, task_ids[0])
    assert (design.status, design.job_id) == (BUDDesignStatus.READY, row["jobId"])
    assert task is not None and task.status == AgentTaskStatus.COMPLETED
