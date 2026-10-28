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

"""Jira: the API token at rest, and import sessions per org.

Jira is never contacted: ``JiraClient.test_connection`` is replaced so a
connect either succeeds with a canned server info or fails the way a bad
token does.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from httpx import AsyncClient

from app.models.jira_import import JiraImportSession, JiraIssueBudMap, MapStatus
from app.services.jira_client import JiraApiError, JiraClient
from tests.integration.settings_support import (
    Factory,
    SeededOrg,
    assert_ciphertext_of,
    load_org,
    make_org,
)

pytestmark = pytest.mark.integration

TOKEN = "ATATT3x-plaintext-jira-token"
CONNECT = "/api/v1/jira/connect"
BODY = {"siteUrl": "https://acme.atlassian.net/", "email": "ops@acme.dev", "apiToken": TOKEN}


@pytest.fixture
def jira_says(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """What the fake ``serverInfo`` call does; set ``error`` to fail it."""
    behaviour: dict[str, Any] = {"error": None}

    async def _test_connection(_self: JiraClient) -> dict[str, Any]:
        if behaviour["error"]:
            raise behaviour["error"]
        return {"baseUrl": "https://acme.atlassian.net", "serverTitle": "Acme Jira"}

    monkeypatch.setattr(JiraClient, "test_connection", _test_connection)
    return behaviour


async def _session(factory: Factory, org: SeededOrg) -> tuple[uuid.UUID, uuid.UUID]:
    """An import session with one review-needed issue, in ``org``."""
    async with factory() as db:
        session = JiraImportSession(
            org_id=org.id,
            jira_project_key="ACME",
            jira_project_name="Acme",
            jira_site_id="https://acme.atlassian.net",
            created_by=org.owner.user_id,
        )
        db.add(session)
        await db.flush()
        entry = JiraIssueBudMap(
            org_id=org.id,
            import_session_id=session.id,
            jira_issue_key="ACME-1",
            jira_issue_id="10001",
            jira_issue_type="Story",
            status=MapStatus.REVIEW_NEEDED,
        )
        db.add(entry)
        await db.commit()
        return session.id, entry.id


async def test_connect_encrypts_the_token_and_never_returns_it(
    client: AsyncClient, pg_session_factory: Factory, jira_says: dict[str, Any]
) -> None:
    org = await make_org(pg_session_factory)
    connected = await client.post(CONNECT, headers=org.owner.headers, json=BODY)
    settings = await client.get("/api/v1/settings/connections", headers=org.owner.headers)

    assert connected.json()["connected"] is True
    assert TOKEN not in connected.text and TOKEN not in settings.text
    jira = settings.json()["jira"]
    assert (jira["enabled"], jira["siteUrl"], jira["email"]) == (
        True,
        "https://acme.atlassian.net",
        "ops@acme.dev",
    )
    stored = (await load_org(pg_session_factory, org.id)).config["jira"]
    assert_ciphertext_of(stored["api_token"], TOKEN)


async def test_a_rejected_token_stores_nothing(
    client: AsyncClient, pg_session_factory: Factory, jira_says: dict[str, Any]
) -> None:
    org = await make_org(pg_session_factory)
    jira_says["error"] = JiraApiError(401, "Unauthorized")
    response = await client.post(CONNECT, headers=org.owner.headers, json=BODY)
    body = response.json()
    assert (body["connected"], body["error"]) == (False, "Unauthorized")
    assert TOKEN not in response.text
    assert "jira" not in (await load_org(pg_session_factory, org.id)).config


async def test_disconnect_removes_the_credentials(
    client: AsyncClient, pg_session_factory: Factory, jira_says: dict[str, Any]
) -> None:
    org = await make_org(pg_session_factory)
    await client.post(CONNECT, headers=org.owner.headers, json=BODY)
    response = await client.delete(CONNECT, headers=org.owner.headers)
    assert response.status_code == 204
    assert "jira" not in (await load_org(pg_session_factory, org.id)).config


async def test_a_developer_cannot_connect_or_disconnect(
    client: AsyncClient, pg_session_factory: Factory, jira_says: dict[str, Any]
) -> None:
    org = await make_org(pg_session_factory)
    connect = await client.post(CONNECT, headers=org.developer.headers, json=BODY)
    disconnect = await client.delete(CONNECT, headers=org.developer.headers)
    assert (connect.status_code, disconnect.status_code) == (403, 403)
    assert "jira" not in (await load_org(pg_session_factory, org.id)).config


async def test_another_orgs_sessions_and_review_items_are_not_found(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    owner_org, other = await make_org(pg_session_factory), await make_org(pg_session_factory)
    session_id, entry_id = await _session(pg_session_factory, owner_org)
    headers = other.owner.headers

    attempts = [
        await client.get(f"/api/v1/jira/sessions/{session_id}", headers=headers),
        await client.post(f"/api/v1/jira/sessions/{session_id}/enrich", headers=headers),
        await client.post(
            f"/api/v1/jira/review/{entry_id}/action", headers=headers, json={"action": "skip"}
        ),
    ]
    listed = await client.get("/api/v1/jira/sessions", headers=headers)

    assert [r.status_code for r in attempts] == [404, 404, 404]
    assert str(session_id) not in listed.text
    async with pg_session_factory() as db:
        entry = await db.get(JiraIssueBudMap, entry_id)
        assert entry is not None and entry.status == MapStatus.REVIEW_NEEDED


async def test_review_actions_on_the_owning_org(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org = await make_org(pg_session_factory)
    _, entry_id = await _session(pg_session_factory, org)
    url = f"/api/v1/jira/review/{entry_id}/action"

    unknown = await client.post(url, headers=org.owner.headers, json={"action": "explode"})
    merge = await client.post(url, headers=org.owner.headers, json={"action": "merge"})
    skip = await client.post(url, headers=org.owner.headers, json={"action": "skip"})
    again = await client.post(url, headers=org.owner.headers, json={"action": "skip"})

    assert (unknown.status_code, merge.status_code) == (400, 400)
    assert "No similar BUD" in merge.json()["detail"]
    assert skip.json() == {"status": "skipped", "mapId": str(entry_id)}
    assert again.status_code == 400
