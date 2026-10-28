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

"""Rows, a slow-commit API client and an isolated job queue for the retry-route tests.

The client's request session waits before each commit, as a real database
round trip does, so a route that queues a job and only then commits gives a
worker time to run first — the race these tests pin.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.router import api_router
from app.core.deps import get_db
from app.core.security import create_access_token
from app.models.agent_skill import AgentSkill, AgentType
from app.models.bud import BUDDesign, BUDDesignStatus, BUDDocument, BUDStatus
from app.models.bud_agent_task import AgentTaskStatus, BUDAgentTask
from app.models.organization import Organization
from app.models.user import OrgToUser, User
from app.repositories.role import RoleRepository
from app.services import job_queue, notification_service
from app.services.job_queue import JobHandler
from app.services.permission_seeder import seed_permissions

Factory = async_sessionmaker[AsyncSession]
COMMIT_LATENCY_SECONDS = 0.2


@dataclass(frozen=True)
class FailedTask:
    """A BUD with a FAILED agent task to retry, and the caller's headers."""

    bud_id: uuid.UUID
    task_id: uuid.UUID
    design_id: uuid.UUID | None
    headers: dict[str, str]


@asynccontextmanager
async def slow_commit_client(factory: Factory) -> AsyncIterator[AsyncClient]:
    """The real API router on a session whose commits take a moment to land."""
    async with factory() as db:
        await seed_permissions(db)
        await db.commit()
    app = FastAPI()
    app.include_router(api_router)

    async def _db() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            commit = session.commit

            async def slow_commit() -> None:
                await asyncio.sleep(COMMIT_LATENCY_SECONDS)
                await commit()

            setattr(session, "commit", slow_commit)  # noqa: B010
            yield session
            await commit()

    app.dependency_overrides[get_db] = _db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http


def _no_notification(*args: object, **kwargs: object) -> None:
    """Stands in for ``send_job_notification``."""


@asynccontextmanager
async def isolated_workers(
    monkeypatch: pytest.MonkeyPatch, handlers: dict[str, JobHandler]
) -> AsyncIterator[None]:
    """Real queue workers for ``handlers`` on a queue no other test shares.

    Job notifications are switched off: they open the app's own database
    session, which these tests do not point at the test database.
    """
    monkeypatch.setattr(notification_service, "send_job_notification", _no_notification)
    monkeypatch.setattr(job_queue, "_registry", {})
    monkeypatch.setattr(job_queue, "_job_store", {})
    monkeypatch.setattr(job_queue, "_running_tasks", {})
    monkeypatch.setattr(job_queue, "_workers", [])
    monkeypatch.setattr(job_queue, "_shutting_down", False)
    for job_type, handler in handlers.items():
        job_queue.register_job_type(job_type, handler)
    await job_queue.start_workers()
    try:
        yield
    finally:
        await job_queue.stop_workers()


async def drain(job_type: str) -> None:
    """Wait until every queued job of ``job_type`` has been handled."""
    _, _, queue = job_queue._registry[job_type]
    await asyncio.wait_for(queue.join(), 5)


async def failed_task(factory: Factory, task_type: str = "closed") -> FailedTask:
    """An org owner, a BUD and a FAILED task of ``task_type`` (with a failed design row
    when the type is ``design``)."""
    tag = uuid.uuid4().hex[:8]
    async with factory() as db:
        org = Organization(name=f"Acme {tag}", slug=f"acme-{tag}", config={})
        user = User(email=f"owner-{tag}@example.test", name="owner", password_hash="x")
        db.add_all([org, user])
        await db.flush()
        role = await RoleRepository(db).get_by_name_system("org_owner")
        assert role is not None
        agent_type = AgentType.DESIGN if task_type == "design" else AgentType.LEARNING
        skill = AgentSkill(
            org_id=org.id, skill_slug="s", agent_type=agent_type, name="S", prompt="p"
        )
        status = BUDStatus.DESIGN if task_type == "design" else BUDStatus.CLOSED
        bud = BUDDocument(org_id=org.id, bud_number=1, title="t", status=status)
        db.add_all([OrgToUser(user_id=user.id, org_id=org.id, role_id=role.id), skill, bud])
        await db.flush()
        task = BUDAgentTask(
            org_id=org.id,
            bud_id=bud.id,
            skill_id=skill.id,
            task_type=task_type,
            status=AgentTaskStatus.FAILED,
        )
        db.add(task)
        design_id = None
        if task_type == "design":
            design = BUDDesign(org_id=org.id, bud_id=bud.id, status=BUDDesignStatus.FAILED)
            db.add(design)
            await db.flush()
            design_id = design.id
        await db.commit()
        token = create_access_token({"sub": str(user.id), "org_id": str(org.id)})
        return FailedTask(bud.id, task.id, design_id, {"Authorization": f"Bearer {token}"})
