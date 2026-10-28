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

"""``POST /buds/{id}/agent-tasks/{task_id}/retry`` commits the new attempt before enqueueing.

A worker for the agent job type is started on an isolated queue. Its handler
only looks the task row up in a fresh session, the way the real handler
starts. The request session's commit is given some latency, as a real
database has, so a route that enqueues before committing loses the race the
same way it does in production.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.router import api_router
from app.core.deps import get_db
from app.core.security import create_access_token
from app.models.agent_skill import AgentSkill, AgentType
from app.models.bud import BUDDocument, BUDStatus
from app.models.bud_agent_task import AgentTaskStatus, BUDAgentTask
from app.models.organization import Organization
from app.models.user import OrgToUser, User
from app.repositories.role import RoleRepository
from app.services import job_queue
from app.services.permission_seeder import seed_permissions

pytestmark = pytest.mark.integration

Factory = async_sessionmaker[AsyncSession]


COMMIT_LATENCY_SECONDS = 0.2


@pytest_asyncio.fixture
async def slow_commit_client(pg_session_factory: Factory) -> AsyncIterator[AsyncClient]:
    """The real API router on a session whose commits take a moment to land."""
    async with pg_session_factory() as db:
        await seed_permissions(db)
        await db.commit()
    app = FastAPI()
    app.include_router(api_router)

    async def _db() -> AsyncIterator[AsyncSession]:
        async with pg_session_factory() as session:
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


@pytest_asyncio.fixture
async def seen_by_worker(
    pg_session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[dict[str, bool]]:
    """A real worker for agent jobs whose handler records whether the task row exists."""
    seen: dict[str, bool] = {}

    async def probe(job_id: str, payload: dict[str, Any]) -> None:
        async with pg_session_factory() as db:
            seen[payload["task_id"]] = (
                await db.get(BUDAgentTask, uuid.UUID(payload["task_id"])) is not None
            )

    monkeypatch.setattr(job_queue, "_registry", {})
    monkeypatch.setattr(job_queue, "_job_store", {})
    monkeypatch.setattr(job_queue, "_running_tasks", {})
    monkeypatch.setattr(job_queue, "_workers", [])
    monkeypatch.setattr(job_queue, "_shutting_down", False)
    job_queue.register_job_type(job_queue.JOB_BUD_AGENT, probe)
    await job_queue.start_workers()
    try:
        yield seen
    finally:
        await job_queue.stop_workers()


async def _failed_task(factory: Factory) -> tuple[uuid.UUID, uuid.UUID, dict[str, str]]:
    """An org owner, a BUD and a FAILED learning task to retry; returns ids and headers."""
    tag = uuid.uuid4().hex[:8]
    async with factory() as db:
        org = Organization(name=f"Acme {tag}", slug=f"acme-{tag}", config={})
        user = User(email=f"owner-{tag}@example.test", name="owner", password_hash="x")
        db.add_all([org, user])
        await db.flush()
        role = await RoleRepository(db).get_by_name_system("org_owner")
        assert role is not None
        skill = AgentSkill(
            org_id=org.id,
            skill_slug="technical-writer",
            agent_type=AgentType.LEARNING,
            name="Writer",
            prompt="p",
        )
        bud = BUDDocument(org_id=org.id, bud_number=1, title="t", status=BUDStatus.CLOSED)
        db.add_all([OrgToUser(user_id=user.id, org_id=org.id, role_id=role.id), skill, bud])
        await db.flush()
        task = BUDAgentTask(
            org_id=org.id,
            bud_id=bud.id,
            skill_id=skill.id,
            task_type="closed",
            status=AgentTaskStatus.FAILED,
        )
        db.add(task)
        await db.commit()
        token = create_access_token({"sub": str(user.id), "org_id": str(org.id)})
        return bud.id, task.id, {"Authorization": f"Bearer {token}"}


async def test_retried_task_is_visible_to_the_worker_that_picks_it_up(
    slow_commit_client: AsyncClient,
    pg_session_factory: Factory,
    seen_by_worker: dict[str, bool],
) -> None:
    """The new attempt's row is committed by the time a worker can run its job."""
    bud_id, task_id, headers = await _failed_task(pg_session_factory)

    response = await slow_commit_client.post(
        f"/api/v1/buds/{bud_id}/agent-tasks/{task_id}/retry", headers=headers
    )
    body = response.json()
    _, _, queue = job_queue._registry[job_queue.JOB_BUD_AGENT]
    await asyncio.wait_for(queue.join(), 5)

    assert (response.status_code, body["attempt"], body["status"]) == (202, 2, "running")
    assert seen_by_worker == {body["id"]: True}
