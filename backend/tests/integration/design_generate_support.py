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

"""Rows, a slow-commit API client and an isolated queue for the design-generate tests.

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
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.router import api_router
from app.core.deps import get_db
from app.core.security import create_access_token
from app.models.agent_skill import AgentSkill, AgentType
from app.models.bud import BUDDocument, BUDStatus
from app.models.organization import Organization
from app.models.tracked_repository import TrackedRepository
from app.models.user import OrgToUser, User
from app.repositories.design_system import DesignSystemRefRepository
from app.repositories.role import RoleRepository
from app.services import job_queue, notification_service
from app.services.job_queue import JobHandler
from app.services.permission_seeder import seed_permissions

Factory = async_sessionmaker[AsyncSession]
COMMIT_LATENCY_SECONDS = 0.2


@dataclass(frozen=True)
class DesignBud:
    """A design-phase BUD with one repo that has a design system."""

    bud_id: uuid.UUID
    repo_id: uuid.UUID
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
async def design_workers(
    monkeypatch: pytest.MonkeyPatch, handler: JobHandler
) -> AsyncIterator[None]:
    """A real worker for design jobs running ``handler``, on a queue no other test shares.

    Job notifications are switched off: they open the app's own database
    session, which these tests do not point at the test database.
    """
    monkeypatch.setattr(notification_service, "send_job_notification", _no_notification)
    monkeypatch.setattr(job_queue, "_registry", {})
    monkeypatch.setattr(job_queue, "_job_store", {})
    monkeypatch.setattr(job_queue, "_running_tasks", {})
    monkeypatch.setattr(job_queue, "_workers", [])
    monkeypatch.setattr(job_queue, "_shutting_down", False)
    job_queue.register_job_type(job_queue.JOB_DESIGN_AGENT, handler)
    await job_queue.start_workers()
    try:
        yield
        _, _, queue = job_queue._registry[job_queue.JOB_DESIGN_AGENT]
        await asyncio.wait_for(queue.join(), 5)
    finally:
        await job_queue.stop_workers()


async def design_bud(factory: Factory) -> DesignBud:
    """An org owner, a designer skill, a repo with a design system and a design-phase BUD."""
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
            skill_slug="designer",
            agent_type=AgentType.DESIGN,
            name="Designer",
            prompt="p",
            is_default=True,
        )
        repo = TrackedRepository(org_id=org.id, path=f"/tmp/{tag}", name="web")
        bud = BUDDocument(org_id=org.id, bud_number=1, title="t", status=BUDStatus.DESIGN)
        db.add_all([OrgToUser(user_id=user.id, org_id=org.id, role_id=role.id), skill, repo, bud])
        await db.flush()
        await DesignSystemRefRepository(db, org_id=org.id).upsert(
            repo_id=repo.id,
            content="# Tokens",
            source_hash="h",
            extracted_at=datetime.now(UTC),
            is_default=True,
        )
        await db.commit()
        token = create_access_token({"sub": str(user.id), "org_id": str(org.id)})
        return DesignBud(bud.id, repo.id, {"Authorization": f"Bearer {token}"})
