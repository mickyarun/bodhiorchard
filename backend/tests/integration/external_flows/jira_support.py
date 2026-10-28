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

"""Jira import over HTTP: connect, discover, import, review — against the fake site."""

from __future__ import annotations

from typing import Any

from httpx import AsyncClient, Response

from tests.fakes.jira import FakeJira, jira_issue
from tests.fakes.seed import Factory, SeededOrg, auth_headers, seed_org
from tests.integration.external_flows.jobs_support import InlineJobs

JIRA = "/api/v1/jira"


def headers(org: SeededOrg) -> dict[str, str]:
    """The org owner's auth headers."""
    return auth_headers(org.owner_id, org.org_id)


async def connect(
    client: AsyncClient, org: SeededOrg, jira: FakeJira, *, token: str | None = None
) -> Response:
    """Save and test the fake site's credentials."""
    body = {"siteUrl": jira.site_url, "email": jira.email, "apiToken": token or jira.api_token}
    return await client.post(f"{JIRA}/connect", json=body, headers=headers(org))


async def discover(
    client: AsyncClient, org: SeededOrg, jobs: InlineJobs, project: str
) -> dict[str, Any]:
    """Run discovery for ``project``; return the session as the API shows it."""
    started = await client.post(
        f"{JIRA}/discover", json={"projectKey": project}, headers=headers(org)
    )
    assert started.status_code == 202, started.text
    await jobs.run_all()
    return await session(client, org, started.json()["sessionId"])


async def start_import(
    client: AsyncClient, org: SeededOrg, jobs: InlineJobs, session_id: str, **config: Any
) -> dict[str, Any]:
    """Start the import for a discovered session, run it, return the session."""
    body = {"sessionId": session_id, **config}
    started = await client.post(f"{JIRA}/import", json=body, headers=headers(org))
    assert started.status_code == 202, started.text
    await jobs.run_all()
    return await session(client, org, session_id)


async def session(client: AsyncClient, org: SeededOrg, session_id: str) -> dict[str, Any]:
    """``GET /jira/sessions/{id}``."""
    resp = await client.get(f"{JIRA}/sessions/{session_id}", headers=headers(org))
    assert resp.status_code == 200, resp.text
    body: dict[str, Any] = resp.json()
    return body


async def review_items(
    client: AsyncClient, org: SeededOrg, session_id: str
) -> dict[str, dict[str, Any]]:
    """The session's review-needed map entries, by Jira key."""
    resp = await client.get(f"{JIRA}/sessions/{session_id}/review-items", headers=headers(org))
    return {item["jiraKey"]: item for item in resp.json()}


async def act(client: AsyncClient, org: SeededOrg, map_id: str, action: str) -> Response:
    """Skip / import / merge one review item."""
    return await client.post(
        f"{JIRA}/review/{map_id}/action", json={"action": action}, headers=headers(org)
    )


def seed_backlog(jira: FakeJira) -> None:
    """An epic with a story under it, a standalone story with points, and a bug."""
    jira.add_issue(
        jira_issue("PAY-1", "Wallet", issue_type="Epic", description="Pay out to wallets")
    )
    child = jira_issue("PAY-2", "Refund to wallet", description="Refunds land in the wallet.")
    child["fields"]["parent"] = {"key": "PAY-1"}
    jira.add_issue(child)
    jira.add_issue(
        jira_issue(
            "PAY-3",
            "Export statements",
            status="Backlog",
            description="Monthly *CSV* export",
            priority={"name": "High"},
            labels=["finance"],
            customfield_10016=5,
        )
    )
    jira.add_issue(jira_issue("PAY-4", "Refund button misaligned", issue_type="Bug"))


async def connected_org(client: AsyncClient, factory: Factory, jira: FakeJira) -> SeededOrg:
    """A fresh org connected to the fake site."""
    org = await seed_org(factory)
    assert (await connect(client, org, jira)).json()["connected"] is True
    return org
