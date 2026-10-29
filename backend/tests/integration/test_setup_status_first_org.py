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

"""``GET /api/setup/status`` names the install's first org, every time.

The login page has no org field: it signs in to the slug this route
returns. The lookup was ``SELECT ... LIMIT 1`` with no order, so with two
orgs Postgres could hand back either. An update rewrites a row at the end
of the table, and after the first org's settings were saved, its people got
"Invalid email or password" because the page now signed in to another org.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.organization import Organization

pytestmark = pytest.mark.integration


async def test_status_keeps_naming_the_first_org_after_it_is_updated(
    pg_session_factory: async_sessionmaker[AsyncSession], client: AsyncClient
) -> None:
    async with pg_session_factory() as db:
        for _ in range(2):
            tag = uuid.uuid4().hex[:8]
            db.add(Organization(name=f"Status {tag}", slug=f"status-{tag}"))
            await db.commit()
        first = await db.scalar(
            select(Organization).order_by(Organization.created_at, Organization.id).limit(1)
        )
        assert first is not None
        first.name = f"{first.name} renamed"
        await db.commit()
        first_slug = first.slug

    response = await client.get("/api/setup/status")

    assert response.status_code == 200
    assert response.json() == {"is_setup_complete": True, "org_slug": first_slug}
