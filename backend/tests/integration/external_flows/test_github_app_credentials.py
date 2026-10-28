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

"""Saving GitHub App credentials: the synchronous ``GET /app`` check and the slug back-fill."""

from __future__ import annotations

import asyncio

import pytest
from httpx import AsyncClient

from app.services import github_app_slug
from tests.fakes.github import FakeGitHub
from tests.fakes.seed import Factory, auth_headers, seed_org
from tests.integration.external_flows.github_support import (
    CONNECTIONS,
    INSTALLABLE,
    fresh_app_id,
    load_org,
    requests_to,
    unique_name,
    update_org,
)

pytestmark = pytest.mark.integration


async def test_valid_credentials_are_checked_with_github_and_the_slug_saved(
    client: AsyncClient, app_sessions: Factory, gh: FakeGitHub
) -> None:
    org = await seed_org(app_sessions)
    headers = auth_headers(org.owner_id, org.org_id)

    resp = await client.patch(
        CONNECTIONS,
        json={"github": {"appId": gh.app_id, "privateKey": gh.private_key_pem}},
        headers=headers,
    )

    assert resp.status_code == 200, resp.text
    github = resp.json()["github"]
    assert (github["status"], github["slug"], github["hasPrivateKey"]) == (
        "awaiting_install",
        gh.app_slug,
        True,
    )
    assert github["installUrl"] == f"https://github.com/apps/{gh.app_slug}/installations/new"
    assert [r.method for r in requests_to(gh, "/app")] == ["GET"]
    assert (await load_org(app_sessions, org.org_id)).github_app_slug == gh.app_slug


@pytest.mark.parametrize(
    ("fault", "status", "code"),
    [
        (401, 400, "github_app_credentials_invalid"),
        (404, 400, "github_app_not_found"),
        (500, 502, "github_unreachable"),
    ],
)
async def test_rejected_credentials_are_reported_and_not_saved(
    fault: int,
    status: int,
    code: str,
    client: AsyncClient,
    app_sessions: Factory,
    gh: FakeGitHub,
) -> None:
    org = await seed_org(app_sessions)
    headers = auth_headers(org.owner_id, org.org_id)
    gh.fail("GET", r"^/app$", fault)

    resp = await client.patch(
        CONNECTIONS,
        json={"github": {"appId": gh.app_id, "privateKey": gh.private_key_pem}},
        headers=headers,
    )

    assert resp.status_code == status
    assert resp.json()["detail"]["error"] == code
    assert ([r.url.path for r in gh.requests], gh.faults.faults) == (["/app"], [])
    saved = await load_org(app_sessions, org.org_id)
    assert (saved.github_app_id, saved.github_app_private_key) == (None, None)
    after = (await client.get(CONNECTIONS, headers=headers)).json()["github"]
    assert after["status"] == "not_configured"


async def test_a_key_that_does_not_belong_to_the_app_id_is_rejected_by_the_jwt_check(
    client: AsyncClient, app_sessions: Factory, gh: FakeGitHub
) -> None:
    org = await seed_org(app_sessions)

    resp = await client.patch(
        CONNECTIONS,
        json={"github": {"appId": fresh_app_id(), "privateKey": gh.private_key_pem}},
        headers=auth_headers(org.owner_id, org.org_id),
    )

    assert resp.status_code == 400
    assert resp.json()["detail"]["error"] == "github_app_credentials_invalid"
    assert [r.url.path for r in gh.requests] == ["/app"]
    saved = await load_org(app_sessions, org.org_id)
    assert (saved.github_app_id, saved.github_app_private_key, saved.github_app_slug) == (
        None,
        None,
        None,
    )


async def test_a_missing_slug_is_back_filled_after_the_first_token_exchange(
    client: AsyncClient, app_sessions: Factory, gh: FakeGitHub
) -> None:
    gh.add_repo(f"acme/{unique_name()}")
    org = await seed_org(app_sessions, github=gh)
    await update_org(app_sessions, org.org_id, github_app_slug=None)

    resp = await client.get(INSTALLABLE, headers=auth_headers(org.owner_id, org.org_id))
    await asyncio.gather(*github_app_slug._BACKGROUND_RETROFIT_TASKS)

    # The picker answered before the slug was known, so it had no install link yet.
    assert (resp.json()["installUrl"], len(resp.json()["repos"])) == (None, 1)
    assert (await load_org(app_sessions, org.org_id)).github_app_slug == gh.app_slug


async def test_the_slug_back_fill_tolerates_github_refusing_the_app_lookup(
    client: AsyncClient, app_sessions: Factory, gh: FakeGitHub
) -> None:
    gh.add_repo(f"acme/{unique_name()}")
    org = await seed_org(app_sessions, github=gh)
    await update_org(app_sessions, org.org_id, github_app_slug=None)
    gh.fail("GET", r"^/app$", 500)

    resp = await client.get(INSTALLABLE, headers=auth_headers(org.owner_id, org.org_id))
    await asyncio.gather(*github_app_slug._BACKGROUND_RETROFIT_TASKS)

    assert resp.status_code == 200
    assert [r.url.path for r in gh.requests if r.url.path == "/app"] == ["/app"]
    assert gh.faults.faults == []
    assert (await load_org(app_sessions, org.org_id)).github_app_slug is None
