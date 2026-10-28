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

"""A rejected bug reports when it was rejected.

``rejectedAt`` is part of the bug response but the serialiser never filled
it, so it was always null even though the column was stamped.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.v1 import bugs as bugs_api
from app.core.security import create_access_token
from app.models.organization import Organization
from app.models.user import OrgToUser, User
from app.repositories.role import RoleRepository

pytestmark = pytest.mark.integration

BUGS = "/api/v1/bugs"


@pytest.fixture(autouse=True)
def _no_embedding() -> Iterator[None]:
    """Keep the embedding model out of bug creation."""

    async def _no_link(*args: object) -> None:
        return None

    with patch.object(bugs_api, "embed_and_link_bug", _no_link):
        yield


async def _manager(factory: async_sessionmaker[AsyncSession]) -> dict[str, str]:
    async with factory() as db:
        org = Organization(name=f"Org {uuid.uuid4()}", slug=f"o-{uuid.uuid4().hex[:10]}")
        user = User(email=f"{uuid.uuid4().hex[:10]}@acme.dev", name="Mia", password_hash="x")
        db.add_all([org, user])
        await db.flush()
        role = await RoleRepository(db).get_by_name_system("manager")
        assert role is not None
        db.add(OrgToUser(user_id=user.id, org_id=org.id, role_id=role.id))
        await db.commit()
    token = create_access_token({"sub": str(user.id), "org_id": str(org.id)})
    return {"Authorization": f"Bearer {token}"}


async def test_rejecting_a_bug_returns_when_it_was_rejected_and_keeps_it(
    client: AsyncClient, pg_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    headers = await _manager(pg_session_factory)
    bug_id = (await client.post(BUGS, json={"title": "x"}, headers=headers)).json()["id"]

    rejected = await client.patch(f"{BUGS}/{bug_id}", json={"status": "rejected"}, headers=headers)
    fetched = await client.get(f"{BUGS}/{bug_id}", headers=headers)

    assert rejected.json()["rejectedAt"] is not None
    assert fetched.json()["rejectedAt"] == rejected.json()["rejectedAt"]


async def test_an_open_bug_has_no_rejection_time(
    client: AsyncClient, pg_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    headers = await _manager(pg_session_factory)
    created = await client.post(BUGS, json={"title": "x"}, headers=headers)
    assert created.json()["rejectedAt"] is None
