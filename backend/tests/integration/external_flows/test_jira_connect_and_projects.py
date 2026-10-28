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

"""Connecting a Jira site and listing its projects, against the fake site."""

from __future__ import annotations

import base64

import pytest
from httpx import AsyncClient

from tests.fakes.jira import FakeJira, jira_issue
from tests.fakes.seed import Factory, seed_org
from tests.integration.external_flows.github_support import load_org
from tests.integration.external_flows.jira_support import JIRA, connect, headers

pytestmark = pytest.mark.integration


async def test_connecting_tests_the_site_and_saves_the_token_encrypted(
    client: AsyncClient, app_sessions: Factory, fake_jira: FakeJira
) -> None:
    org = await seed_org(app_sessions)

    resp = await connect(client, org, fake_jira)

    assert resp.json() == {
        "connected": True,
        "cloudId": fake_jira.site_url,
        "siteName": "Fake Jira",
        "error": None,
    }
    (probe,) = fake_jira.requests
    expected = base64.b64encode(f"{fake_jira.email}:{fake_jira.api_token}".encode()).decode()
    assert (probe.url.path, probe.headers["authorization"]) == (
        "/rest/api/3/serverInfo",
        f"Basic {expected}",
    )
    saved = ((await load_org(app_sessions, org.org_id)).config or {})["jira"]
    assert (saved["site_url"], saved["email"]) == (fake_jira.site_url, fake_jira.email)
    assert saved["api_token"] != fake_jira.api_token
    shown = await client.get("/api/v1/settings/connections", headers=headers(org))
    assert shown.json()["jira"]["enabled"] is True
    assert fake_jira.api_token not in shown.text


async def test_a_wrong_token_is_reported_and_nothing_is_saved(
    client: AsyncClient, app_sessions: Factory, fake_jira: FakeJira
) -> None:
    org = await seed_org(app_sessions)

    resp = await connect(client, org, fake_jira, token="revoked")

    body = resp.json()
    assert (resp.status_code, body["connected"]) == (200, False)
    assert "returned 401" in body["error"]
    assert "jira" not in ((await load_org(app_sessions, org.org_id)).config or {})


async def test_a_rate_limited_probe_is_retried_after_the_advertised_wait(
    client: AsyncClient, app_sessions: Factory, fake_jira: FakeJira
) -> None:
    org = await seed_org(app_sessions)
    fake_jira.fail(r"/serverInfo$", 429)

    resp = await connect(client, org, fake_jira)

    assert resp.json()["connected"] is True
    assert [r.url.path for r in fake_jira.requests] == ["/rest/api/3/serverInfo"] * 2


async def test_projects_are_listed_from_the_connected_site(
    client: AsyncClient, app_sessions: Factory, fake_jira: FakeJira
) -> None:
    fake_jira.add_issue(jira_issue("PAY-1", "Wallet refunds"))
    fake_jira.add_issue(jira_issue("OPS-1", "Pager rota"))
    fake_jira.projects["PAY"] = "Payments"
    org = await seed_org(app_sessions)
    await connect(client, org, fake_jira)

    resp = await client.get(f"{JIRA}/projects", headers=headers(org))

    assert resp.json() == [
        {"key": "PAY", "name": "Payments", "lead": None},
        {"key": "OPS", "name": "Project OPS", "lead": None},
    ]


async def test_projects_need_a_connected_site(client: AsyncClient, app_sessions: Factory) -> None:
    org = await seed_org(app_sessions)

    resp = await client.get(f"{JIRA}/projects", headers=headers(org))

    assert resp.status_code == 400
    assert "not connected" in resp.json()["detail"]


async def test_disconnecting_forgets_the_site(
    client: AsyncClient, app_sessions: Factory, fake_jira: FakeJira
) -> None:
    org = await seed_org(app_sessions)
    await connect(client, org, fake_jira)

    gone = await client.delete(f"{JIRA}/connect", headers=headers(org))
    projects = await client.get(f"{JIRA}/projects", headers=headers(org))

    assert (gone.status_code, projects.status_code) == (204, 400)
    assert len(fake_jira.requests) == 1
