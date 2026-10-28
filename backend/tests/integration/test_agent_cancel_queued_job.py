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

"""Cancelling an agent task or design whose job is still queued stops the job.

The cancel services only signalled a job that was already running. A job
still waiting behind a busy worker had its rows marked failed, then ran
anyway once the worker freed up. A real queue with one busy worker is used
here; the handler only records that it ran.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.agent_skill import AgentSkill, AgentType
from app.models.bud import BUDDesign, BUDDesignStatus, BUDDocument, BUDStatus
from app.models.bud_agent_task import AgentTaskStatus, BUDAgentTask
from app.models.organization import Organization
from app.schemas.jobs import JobState
from app.services import event_bus, job_queue
from app.services.agent_task_cancel import cancel_design, cancel_task

pytestmark = pytest.mark.integration

Factory = async_sessionmaker[AsyncSession]
JOB = "queued_agent_job"


class _Queue:
    """One worker held inside a busy job; records every job that runs."""

    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.ran: list[str] = []

    async def handler(self, job_id: str, payload: dict[str, Any]) -> None:
        self.ran.append(payload["name"])
        if payload["name"] == "busy":
            self.started.set()
            await self.release.wait()
        job_queue.update_job(job_id, state=JobState.COMPLETED)

    async def drain(self) -> None:
        self.release.set()
        _, _, queue = job_queue._registry[JOB]
        await asyncio.wait_for(queue.join(), timeout=5)


@pytest.fixture
async def busy_queue(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[_Queue]:
    """A private job queue whose only worker is busy before the test starts."""
    monkeypatch.setattr(job_queue, "_registry", {})
    monkeypatch.setattr(job_queue, "_job_store", {})
    monkeypatch.setattr(job_queue, "_running_tasks", {})
    monkeypatch.setattr(job_queue, "_workers", [])
    monkeypatch.setattr(job_queue, "_shutting_down", False)
    monkeypatch.setattr(event_bus, "publish", lambda topic, data: None)
    queue = _Queue()
    job_queue.register_job_type(JOB, queue.handler, worker_count=1)
    await job_queue.start_workers()
    job_queue.create_job(JOB, payload={"name": "busy"})
    await asyncio.wait_for(queue.started.wait(), timeout=5)
    yield queue
    await job_queue.stop_workers()


async def _rows(factory: Factory, job_id: str) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Org, a RUNNING design task and a GENERATING design, both on ``job_id``."""
    async with factory() as db:
        org = Organization(name=f"Q {uuid.uuid4()}", slug=f"q-{uuid.uuid4().hex[:10]}")
        db.add(org)
        await db.flush()
        skill = AgentSkill(
            org_id=org.id, skill_slug="designer", agent_type=AgentType.DESIGN, name="D", prompt="p"
        )
        bud = BUDDocument(org_id=org.id, bud_number=1, title="t", status=BUDStatus.DESIGN)
        db.add_all([skill, bud])
        await db.flush()
        task = BUDAgentTask(
            org_id=org.id,
            bud_id=bud.id,
            skill_id=skill.id,
            task_type="design",
            status=AgentTaskStatus.RUNNING,
            job_id=job_id,
        )
        design = BUDDesign(
            org_id=org.id, bud_id=bud.id, status=BUDDesignStatus.GENERATING, job_id=job_id
        )
        db.add_all([task, design])
        await db.commit()
        return org.id, task.id, design.id


async def test_cancel_task_drops_its_queued_job(
    busy_queue: _Queue, pg_session_factory: Factory
) -> None:
    """The task and its design end failed and the queued job never runs."""
    queued = job_queue.create_job(JOB, payload={"name": "agent"})
    org_id, task_id, design_id = await _rows(pg_session_factory, queued.job_id)

    async with pg_session_factory() as db:
        task = await db.get(BUDAgentTask, task_id)
        assert task is not None
        await cancel_task(db, org_id=org_id, task=task, reason="Stopped")
    await busy_queue.drain()

    assert busy_queue.ran == ["busy"]
    assert job_queue.get_job(queued.job_id).state == JobState.CANCELLED  # type: ignore[union-attr]
    async with pg_session_factory() as db:
        task_row = await db.get(BUDAgentTask, task_id)
        design_row = await db.get(BUDDesign, design_id)
        assert task_row is not None and design_row is not None
        assert (task_row.status, design_row.status) == ("failed", BUDDesignStatus.FAILED)


async def test_cancel_design_drops_its_queued_job(
    busy_queue: _Queue, pg_session_factory: Factory
) -> None:
    """A per-repo design cancel also stops its queued job."""
    queued = job_queue.create_job(JOB, payload={"name": "design"})
    org_id, task_id, design_id = await _rows(pg_session_factory, queued.job_id)

    async with pg_session_factory() as db:
        design = await db.get(BUDDesign, design_id)
        assert design is not None
        await cancel_design(db, org_id=org_id, design=design, reason="Stopped")
    await busy_queue.drain()

    assert busy_queue.ran == ["busy"]
    async with pg_session_factory() as db:
        design_row = await db.get(BUDDesign, design_id)
        task_row = await db.get(BUDAgentTask, task_id)
        assert design_row is not None and task_row is not None
        assert (design_row.status, task_row.status) == (BUDDesignStatus.FAILED, "failed")
