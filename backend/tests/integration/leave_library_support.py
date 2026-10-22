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

"""Setup shared by the leave type library tests."""

from __future__ import annotations

import uuid

from httpx import AsyncClient

from app.schemas.leave_policy import PolicyWrite
from app.services.leave.policy_admin import create_policy
from tests.integration.leave_support import Factory


async def add_policy(factory: Factory, org: uuid.UUID, actor: uuid.UUID, name: str) -> uuid.UUID:
    """A second policy in ``org``, created by ``actor``."""
    async with factory() as db:
        policy = await create_policy(db, org, actor, PolicyWrite(name=name))  # type: ignore[call-arg]
        await db.commit()
        return policy.id


async def library_sick(client: AsyncClient, auth: dict[str, str]) -> str:
    """A library entry "Sick" (SL), 4 days a year by default; returns its id."""
    body = {"name": "Sick", "code": "SL", "annual_quota_days": "4"}
    response = await client.post("/api/v1/leave/library-types", json=body, headers=auth)
    assert response.status_code == 201, response.text
    return str(response.json()["id"])
