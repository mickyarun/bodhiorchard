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

"""The repo picker over HTTP: installable repos and branches from the App installation."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.fakes.git_repo import LocalGitRepo
from tests.fakes.github import FakeGitHub
from tests.fakes.seed import Factory, auth_headers, seed_org, seed_repo
from tests.integration.external_flows.github_support import (
    INSTALLABLE,
    bearer_tokens,
    drop_app_credentials,
    fresh_app_id,
    requests_to,
    set_installation,
    unique_name,
)

pytestmark = pytest.mark.integration


async def test_installable_repos_page_through_and_mark_the_tracked_one(
    client: AsyncClient, app_sessions: Factory, gh: FakeGitHub, git_repo: LocalGitRepo
) -> None:
    gh.max_page_size = 2  # three repos, two pages
    shop, billing, web = (f"acme/{unique_name(n)}" for n in ("shop", "billing", "web"))
    for full_name in (shop, billing, web):
        gh.add_repo(full_name)
    org = await seed_org(app_sessions, github=gh)
    await seed_repo(app_sessions, org.org_id, git_repo, full_name=billing)

    resp = await client.get(INSTALLABLE, headers=auth_headers(org.owner_id, org.org_id))

    assert resp.status_code == 200
    body = resp.json()
    assert body["appInstallState"] == "ready"
    assert body["installUrl"] == f"https://github.com/apps/{gh.app_slug}/installations/new"
    assert [(r["fullName"], r["alreadyTracked"]) for r in body["repos"]] == [
        (shop, False),
        (billing, True),
        (web, False),
    ]
    assert body["repos"][0]["pushedAt"].startswith("2026-01-02T03:04:05")
    # Two pages, both with the token minted from the App JWT.
    assert bearer_tokens(gh, "/installation/repositories") == gh.issued_tokens * 2


async def test_the_installation_token_is_minted_once_for_repeated_picker_loads(
    client: AsyncClient, app_sessions: Factory, gh: FakeGitHub
) -> None:
    gh.add_repo(f"acme/{unique_name()}")
    org = await seed_org(app_sessions, github=gh)
    headers = auth_headers(org.owner_id, org.org_id)

    for _ in range(3):
        assert (await client.get(INSTALLABLE, headers=headers)).status_code == 200

    assert len(gh.issued_tokens) == 1
    assert len(requests_to(gh, "/access_tokens")) == 1


async def test_an_org_without_app_credentials_gets_the_setup_state_and_no_github_call(
    client: AsyncClient, app_sessions: Factory, gh: FakeGitHub
) -> None:
    org = await seed_org(app_sessions, github=gh)
    await drop_app_credentials(app_sessions, org.org_id)

    resp = await client.get(INSTALLABLE, headers=auth_headers(org.owner_id, org.org_id))

    assert resp.json() == {"appInstallState": "no_credentials", "installUrl": None, "repos": []}
    assert gh.requests == []


async def test_an_app_not_yet_installed_gets_the_install_link_and_no_github_call(
    client: AsyncClient, app_sessions: Factory, gh: FakeGitHub
) -> None:
    org = await seed_org(app_sessions, github=gh)
    await set_installation(app_sessions, org.org_id, None)

    resp = await client.get(INSTALLABLE, headers=auth_headers(org.owner_id, org.org_id))

    body = resp.json()
    assert (body["appInstallState"], body["repos"]) == ("no_install", [])
    assert body["installUrl"].endswith(f"/apps/{gh.app_slug}/installations/new")
    assert gh.requests == []


@pytest.mark.parametrize("failure", ["wrong_app_id", "unknown_installation", "rate_limited"])
async def test_a_failed_token_exchange_lists_no_repos_and_never_lists_with_a_bad_token(
    failure: str, client: AsyncClient, app_sessions: Factory, gh: FakeGitHub
) -> None:
    gh.add_repo(f"acme/{unique_name()}")
    org = await seed_org(app_sessions, github=gh)
    if failure == "wrong_app_id":
        gh.app_id = fresh_app_id()  # the JWT's issuer no longer matches the App: 401
    elif failure == "unknown_installation":
        await set_installation(app_sessions, org.org_id, gh.installation_id + 1)
    else:
        gh.rate_limit("POST", r"/access_tokens$")

    resp = await client.get(INSTALLABLE, headers=auth_headers(org.owner_id, org.org_id))

    assert resp.status_code == 200
    assert (resp.json()["appInstallState"], resp.json()["repos"]) == ("ready", [])
    assert gh.issued_tokens == []
    assert requests_to(gh, "/installation/repositories") == []


@pytest.mark.xfail(
    strict=True,
    reason="a rate-limited repo listing escapes the picker as a 500, "
    "fixed by branch fix/installable-repos-upstream-errors",
)
async def test_a_rate_limited_repo_listing_is_explained_not_a_server_error(
    client: AsyncClient, app_sessions: Factory, gh: FakeGitHub
) -> None:
    gh.add_repo(f"acme/{unique_name()}")
    org = await seed_org(app_sessions, github=gh)
    gh.rate_limit("GET", r"/installation/repositories$")

    resp = await client.get(INSTALLABLE, headers=auth_headers(org.owner_id, org.org_id))

    assert resp.status_code == 429
    assert "rate limit" in resp.json()["detail"]
    assert gh.faults.faults == []


async def test_branches_of_an_installable_repo_follow_pagination(
    client: AsyncClient, app_sessions: Factory, gh: FakeGitHub
) -> None:
    gh.max_page_size = 2  # three branches, two pages
    full_name = f"acme/{unique_name()}"
    gh.add_repo(full_name, "main", "develop", "release/uat")
    org = await seed_org(app_sessions, github=gh)

    resp = await client.get(
        f"{INSTALLABLE}/{full_name}/branches", headers=auth_headers(org.owner_id, org.org_id)
    )

    assert resp.status_code == 200
    assert resp.json() == {"branches": ["main", "develop", "release/uat"]}
    assert len(requests_to(gh, f"/repos/{full_name}/branches")) == 2


async def test_branches_of_a_repo_outside_the_installation_are_refused(
    client: AsyncClient, app_sessions: Factory, gh: FakeGitHub
) -> None:
    gh.add_repo(f"acme/{unique_name()}")
    org = await seed_org(app_sessions, github=gh)

    resp = await client.get(
        f"{INSTALLABLE}/other-co/secret/branches", headers=auth_headers(org.owner_id, org.org_id)
    )

    assert resp.status_code == 404
    assert requests_to(gh, "/branches") == []


async def test_branches_need_a_ready_installation(
    client: AsyncClient, app_sessions: Factory, gh: FakeGitHub
) -> None:
    full_name = f"acme/{unique_name()}"
    gh.add_repo(full_name)
    org = await seed_org(app_sessions, github=gh)
    await set_installation(app_sessions, org.org_id, None)

    resp = await client.get(
        f"{INSTALLABLE}/{full_name}/branches", headers=auth_headers(org.owner_id, org.org_id)
    )

    assert resp.status_code == 400
    assert gh.requests == []
