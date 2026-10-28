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

"""``POST /buds/{id}/agent-tasks/{task_id}/retry`` commits before it queues, then stays out.

Workers run stand-in handlers that do what the real ones do first or fastest:
look the task row up, fail the task at once, or finish a design. The request's
commits are slowed (see ``agent_retry_support``) so any write the route makes
after queueing lands after the handler's.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from app.models.bud import BUDDesign, BUDDesignStatus
from app.models.bud_agent_task import AgentTaskStatus, BUDAgentTask
from app.services import job_queue
from tests.integration.agent_retry_support import (
    Factory,
    drain,
    failed_task,
    isolated_workers,
    slow_commit_client,
)

pytestmark = pytest.mark.integration


async def _task(factory: Factory, task_id: uuid.UUID) -> BUDAgentTask:
    async with factory() as db:
        task = await db.get(BUDAgentTask, task_id)
        assert task is not None
        return task


async def test_retried_task_is_visible_to_the_worker_that_picks_it_up(
    pg_session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The new attempt's row is committed by the time a worker can run its job."""
    seen: dict[str, bool] = {}

    async def probe(job_id: str, payload: dict[str, Any]) -> None:
        async with pg_session_factory() as db:
            row = await db.get(BUDAgentTask, uuid.UUID(payload["task_id"]))
            seen[payload["task_id"]] = row is not None

    retry = await failed_task(pg_session_factory)
    async with (
        isolated_workers(monkeypatch, {job_queue.JOB_BUD_AGENT: probe}),
        slow_commit_client(pg_session_factory) as client,
    ):
        response = await client.post(
            f"/api/v1/buds/{retry.bud_id}/agent-tasks/{retry.task_id}/retry",
            headers=retry.headers,
        )
        await drain(job_queue.JOB_BUD_AGENT)

    body = response.json()
    assert (response.status_code, body["attempt"]) == (202, 2)
    assert seen == {body["id"]: True}


async def test_handler_that_fails_fast_is_not_overwritten_by_the_route(
    pg_session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A handler that fails the task at once (BUD gone, no repos) keeps it FAILED."""

    async def fail_at_once(job_id: str, payload: dict[str, Any]) -> None:
        async with pg_session_factory() as db:
            task = await db.get(BUDAgentTask, uuid.UUID(payload["task_id"]))
            assert task is not None
            task.status = AgentTaskStatus.FAILED
            task.error_message = "BUD not found"
            await db.commit()

    retry = await failed_task(pg_session_factory)
    async with (
        isolated_workers(monkeypatch, {job_queue.JOB_BUD_AGENT: fail_at_once}),
        slow_commit_client(pg_session_factory) as client,
    ):
        response = await client.post(
            f"/api/v1/buds/{retry.bud_id}/agent-tasks/{retry.task_id}/retry",
            headers=retry.headers,
        )
        await drain(job_queue.JOB_BUD_AGENT)

    new_task = await _task(pg_session_factory, uuid.UUID(response.json()["id"]))
    assert (new_task.status, new_task.error_message) == (AgentTaskStatus.FAILED, "BUD not found")
    assert new_task.job_id is not None


async def test_design_retry_does_not_overwrite_a_design_that_already_finished(
    pg_session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A design job that lands its wireframe first keeps READY and its task COMPLETED."""

    async def finish_design(job_id: str, payload: dict[str, Any]) -> None:
        async with pg_session_factory() as db:
            design = await db.get(BUDDesign, uuid.UUID(payload["design_id"]))
            task = await db.get(BUDAgentTask, uuid.UUID(payload["task_id"]))
            assert design is not None and task is not None
            design.status = BUDDesignStatus.READY
            design.design_html = "<html></html>"
            task.status = AgentTaskStatus.COMPLETED
            await db.commit()

    retry = await failed_task(pg_session_factory, "design")
    async with (
        isolated_workers(monkeypatch, {job_queue.JOB_DESIGN_AGENT: finish_design}),
        slow_commit_client(pg_session_factory) as client,
    ):
        response = await client.post(
            f"/api/v1/buds/{retry.bud_id}/agent-tasks/{retry.task_id}/retry",
            headers=retry.headers,
        )
        await drain(job_queue.JOB_DESIGN_AGENT)

    assert response.status_code == 202, response.text
    new_task = await _task(pg_session_factory, uuid.UUID(response.json()["id"]))
    assert new_task.status == AgentTaskStatus.COMPLETED
    async with pg_session_factory() as db:
        design = await db.get(BUDDesign, retry.design_id)
    assert design is not None
    assert design.status == BUDDesignStatus.READY
    assert design.job_id == new_task.job_id
