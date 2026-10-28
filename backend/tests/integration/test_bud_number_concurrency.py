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

"""Concurrent ``POST /buds`` in one org must all succeed with distinct numbers.

``next_bud_number`` reads ``max + 1``; without serialisation two creates
read the same max and the second fails on ``uq_bud_org_number`` (a 500).
"""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.security import create_access_token
from app.models.organization import Organization
from app.models.user import OrgToUser, User
from app.repositories.role import RoleRepository
from app.services.embedding_service import embedding_service

pytestmark = pytest.mark.integration


async def _org_with_pm(factory: async_sessionmaker[AsyncSession]) -> tuple[uuid.UUID, str]:
    """A fresh org with one PM; returns the org id and the PM's bearer token."""
    async with factory() as db:
        org = Organization(name=f"Num {uuid.uuid4()}", slug=f"num-{uuid.uuid4().hex[:10]}")
        user = User(email=f"pm-{uuid.uuid4().hex[:8]}@example.com", name="pm", password_hash="x")
        db.add_all([org, user])
        await db.flush()
        role = await RoleRepository(db).get_by_name_system("pm")
        assert role is not None
        db.add(OrgToUser(user_id=user.id, org_id=org.id, role_id=role.id))
        await db.commit()
        token = create_access_token({"sub": str(user.id), "org_id": str(org.id)})
        return org.id, token


async def test_concurrent_creates_get_consecutive_numbers(
    client: AsyncClient, pg_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """Three simultaneous creates: all 201, numbered 1, 2 and 3."""
    _org, token = await _org_with_pm(pg_session_factory)
    headers = {"Authorization": f"Bearer {token}"}

    with patch.object(embedding_service, "embed", new=AsyncMock(return_value=[0.0] * 384)):
        responses = await asyncio.gather(
            *(
                client.post("/api/v1/buds/", json={"title": f"Race {i}"}, headers=headers)
                for i in range(3)
            )
        )

    assert [r.status_code for r in responses] == [201, 201, 201]
    assert sorted(r.json()["bud_number"] for r in responses) == [1, 2, 3]
