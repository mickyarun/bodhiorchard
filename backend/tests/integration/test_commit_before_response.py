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

"""A request's commit lands before its response reaches the client.

The test runs the real ``get_db`` with no override, swapping only the
session factory for one whose commits are slowed, and reads through a
transport that returns as soon as the response is sent. If the commit ran
after the response (a plain ``yield`` dependency on FastAPI 0.118+), the
read straight after the create would miss the new row.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from app import database
from app.api.router import api_router
from app.services.permission_seeder import seed_permissions
from tests.fakes.seed import Factory, auth_headers, seed_org
from tests.integration.response_first_transport import ResponseFirstTransport
from tests.integration.runner_internals.slow_commit_support import slow_commit_session

pytestmark = pytest.mark.integration


async def test_a_created_row_is_readable_as_soon_as_the_create_responds(
    pg_session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A team read right after its 201 is found, not a 404."""
    async with pg_session_factory() as db:
        await seed_permissions(db)
        await db.commit()
    org = await seed_org(pg_session_factory)
    monkeypatch.setattr(
        database, "AsyncSessionLocal", lambda: slow_commit_session(pg_session_factory)
    )
    app = FastAPI()
    app.include_router(api_router)
    headers = auth_headers(org.owner_id, org.org_id)

    transport = ResponseFirstTransport(app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            "/api/v1/teams", json={"name": f"Platform {uuid.uuid4().hex[:6]}"}, headers=headers
        )
        read = await client.get(f"/api/v1/teams/{created.json()['id']}", headers=headers)

    assert (created.status_code, read.status_code) == (201, 200)
