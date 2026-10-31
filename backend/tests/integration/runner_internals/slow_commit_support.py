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

"""An API client whose request session takes a moment to commit.

A route that queues a job and only then commits gives a worker time to run
first; with real database latency that race is lost in production, and this
client makes it lose every time in a test.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.router import api_router
from app.core.deps import get_db
from app.services.permission_seeder import seed_permissions
from tests.fakes.seed import Factory

COMMIT_LATENCY_SECONDS = 0.2


def slow_commit_session(factory: Factory) -> AsyncSession:
    """A session from ``factory`` that waits before each commit."""
    session = factory()
    commit = session.commit

    async def slow_commit() -> None:
        await asyncio.sleep(COMMIT_LATENCY_SECONDS)
        await commit()

    setattr(session, "commit", slow_commit)  # noqa: B010
    return session


@asynccontextmanager
async def slow_commit_client(factory: Factory) -> AsyncIterator[AsyncClient]:
    """The real API router on sessions that wait before each commit."""
    async with factory() as db:
        await seed_permissions(db)
        await db.commit()
    app = FastAPI()
    app.include_router(api_router)

    async def _db() -> AsyncIterator[AsyncSession]:
        async with slow_commit_session(factory) as session:
            yield session
            await session.commit()

    app.dependency_overrides[get_db] = _db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http
