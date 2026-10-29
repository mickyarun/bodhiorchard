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

"""The member directory lists every member, whatever address is stored for them.

Members created from git history can carry addresses a strict email check
refuses, such as a laptop's ``name@host.local`` or ``root@localhost``. The
directory only reads stored rows, so one such member must not break the
list for everyone.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import update

from app.models.user import User
from tests.fakes.seed import Factory, auth_headers, seed_member, seed_org

pytestmark = pytest.mark.integration

DIRECTORY = "/api/v1/members/directory"


async def test_directory_lists_members_with_loose_stored_emails(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org = await seed_org(pg_session_factory)
    laptop = await seed_member(pg_session_factory, org.org_id, "laptop")
    local = await seed_member(pg_session_factory, org.org_id, "local")
    stored = {laptop: "dev@Dev-MacBook-Pro.local", local: "root@localhost"}
    async with pg_session_factory() as db:
        for user_id, email in stored.items():
            await db.execute(update(User).where(User.id == user_id).values(email=email))
        await db.commit()

    response = await client.get(DIRECTORY, headers=auth_headers(org.owner_id, org.org_id))

    assert response.status_code == 200
    emails = {row["id"]: row["email"] for row in response.json()}
    assert {str(k): v for k, v in stored.items()}.items() <= emails.items()
    assert str(org.owner_id) in emails
