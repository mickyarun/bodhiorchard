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

"""``GET /jira/projects`` when Jira refuses the call after the site was connected.

A token revoked in Atlassian after connecting used to escape the route as
an unhandled ``JiraApiError`` (a bare 500); the settings page could not tell
the admin to reconnect.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.encryption import encrypt_secret
from app.core.security import create_access_token
from app.models.organization import Organization
from app.models.user import OrgToUser, User
from app.repositories.role import RoleRepository
from app.services.jira_client import JiraApiError, JiraClient

pytestmark = pytest.mark.integration
Factory = async_sessionmaker[AsyncSession]
URL = "/api/v1/jira/projects"


async def _connected_owner(factory: Factory) -> dict[str, str]:
    """An org owner whose org has Jira credentials saved; returns auth headers."""
    tag = uuid.uuid4().hex[:8]
    jira = {
        "site_id": "https://acme-test.atlassian.net",
        "site_url": "https://acme-test.atlassian.net",
        "email": "pm@acme.dev",
        "api_token": encrypt_secret("jira-token"),
        "connected_at": datetime.now(UTC).isoformat(),
    }
    async with factory() as db:
        org = Organization(name=f"Jira {tag}", slug=f"jira-{tag}", config={"jira": jira})
        user = User(email=f"owner-{tag}@acme.dev", name="Owner", password_hash="x")
        db.add_all([org, user])
        await db.flush()
        role = await RoleRepository(db).get_by_name_system("org_owner")
        assert role is not None
        db.add(OrgToUser(user_id=user.id, org_id=org.id, role_id=role.id))
        await db.commit()
        token = create_access_token({"sub": str(user.id), "org_id": str(org.id)})
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.parametrize(
    ("jira_status", "status", "phrase"),
    [(401, 400, "Reconnect Jira"), (403, 400, "Reconnect Jira"), (0, 502, "did not answer")],
)
async def test_a_jira_refusal_is_explained_instead_of_a_server_error(
    jira_status: int,
    status: int,
    phrase: str,
    client: AsyncClient,
    pg_session_factory: Factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = await _connected_owner(pg_session_factory)

    async def refused(self: JiraClient) -> list[dict[str, str]]:
        raise JiraApiError(jira_status, "Jira API GET /rest/api/3/project/search failed")

    monkeypatch.setattr(JiraClient, "list_projects", refused)

    resp = await client.get(URL, headers=headers)

    assert resp.status_code == status
    assert phrase in resp.json()["detail"]


async def test_projects_still_list_when_jira_answers(
    client: AsyncClient, pg_session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = await _connected_owner(pg_session_factory)

    async def listed(self: JiraClient) -> list[dict[str, object]]:
        return [{"key": "PAY", "name": "Payments", "lead": {"displayName": "Riya"}}]

    monkeypatch.setattr(JiraClient, "list_projects", listed)

    resp = await client.get(URL, headers=headers)

    assert resp.json() == [{"key": "PAY", "name": "Payments", "lead": "Riya"}]
