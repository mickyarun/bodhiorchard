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

"""The GitHub organisation roster for the invite flow, read through the installation."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.fakes.github import FakeGitHub
from tests.fakes.http_router import FakeHttpRouter
from tests.fakes.seed import Factory, SeededOrg, auth_headers, seed_member, seed_org
from tests.integration.external_flows.github_support import (
    ORG_MEMBERS,
    bearer_tokens,
    page_org_members,
    requests_to,
    set_github_org,
    set_github_username,
)

pytestmark = pytest.mark.integration


async def _org_with_roster(factory: Factory, gh: FakeGitHub) -> SeededOrg:
    gh.add_member("octo-dev", "Octo Dev", "octo@acme.dev")
    gh.add_member("quiet-dev")  # no public name or email
    org = await seed_org(factory, github=gh)
    await set_github_org(factory, org.org_id, "acme")
    return org


async def test_members_come_back_with_profiles_and_the_already_added_flag(
    client: AsyncClient, app_sessions: Factory, gh: FakeGitHub
) -> None:
    org = await _org_with_roster(app_sessions, gh)
    member = await seed_member(app_sessions, org.org_id, "octo")
    await set_github_username(app_sessions, member, "Octo-Dev")

    resp = await client.get(ORG_MEMBERS, headers=auth_headers(org.owner_id, org.org_id))

    assert resp.status_code == 200
    by_login = {m["login"]: m for m in resp.json()}
    assert by_login["octo-dev"] == {
        "login": "octo-dev",
        "name": "Octo Dev",
        "avatar_url": "",
        "email": "octo@acme.dev",
        "already_added": True,
    }
    assert (by_login["quiet-dev"]["name"], by_login["quiet-dev"]["email"]) == ("quiet-dev", None)
    assert by_login["quiet-dev"]["already_added"] is False
    assert set(bearer_tokens(gh, "/users/")) == set(gh.issued_tokens)
    assert requests_to(gh, "/orgs/acme/members")[0].url.params["per_page"] == "100"


@pytest.mark.xfail(
    strict=True,
    reason="the roster reads one page of 100 and never follows Link, "
    "fixed by branch fix/github-org-members-pagination",
)
async def test_a_roster_past_one_page_comes_back_whole(
    client: AsyncClient, app_sessions: Factory, gh: FakeGitHub, http_router: FakeHttpRouter
) -> None:
    page_org_members(http_router, gh)
    logins = [f"dev-{n:03d}" for n in range(130)]
    for login in logins:
        gh.add_member(login)
    org = await seed_org(app_sessions, github=gh)
    await set_github_org(app_sessions, org.org_id, "acme")

    resp = await client.get(ORG_MEMBERS, headers=auth_headers(org.owner_id, org.org_id))

    assert sorted(m["login"] for m in resp.json()) == logins
    assert len(requests_to(gh, "/orgs/acme/members")) == 2


async def test_one_failing_profile_does_not_blank_the_roster(
    client: AsyncClient, app_sessions: Factory, gh: FakeGitHub
) -> None:
    org = await _org_with_roster(app_sessions, gh)
    gh.fail("GET", r"^/users/octo-dev$", 500)

    resp = await client.get(ORG_MEMBERS, headers=auth_headers(org.owner_id, org.org_id))

    assert resp.status_code == 200
    by_login = {m["login"]: m for m in resp.json()}
    assert (by_login["octo-dev"]["name"], by_login["octo-dev"]["email"]) == ("octo-dev", None)
    assert len(by_login) == 2


async def test_an_empty_organisation_returns_an_empty_roster(
    client: AsyncClient, app_sessions: Factory, gh: FakeGitHub
) -> None:
    org = await seed_org(app_sessions, github=gh)
    await set_github_org(app_sessions, org.org_id, "acme")

    resp = await client.get(ORG_MEMBERS, headers=auth_headers(org.owner_id, org.org_id))

    assert (resp.status_code, resp.json()) == (200, [])
    assert requests_to(gh, "/users/") == []


@pytest.mark.parametrize(
    ("fault", "status", "phrase"),
    [(401, 401, "unauthorized"), (403, 403, "permissions"), (404, 404, "'acme' not found")],
)
async def test_github_refusals_on_the_member_list_are_explained(
    fault: int,
    status: int,
    phrase: str,
    client: AsyncClient,
    app_sessions: Factory,
    gh: FakeGitHub,
) -> None:
    org = await _org_with_roster(app_sessions, gh)
    gh.fail("GET", r"^/orgs/acme/members$", fault)

    resp = await client.get(ORG_MEMBERS, headers=auth_headers(org.owner_id, org.org_id))

    assert resp.status_code == status
    assert phrase in resp.json()["detail"]
    assert requests_to(gh, "/users/") == []


async def test_members_need_the_app_and_an_organisation_name(
    client: AsyncClient, app_sessions: Factory, gh: FakeGitHub
) -> None:
    no_app = await seed_org(app_sessions)
    no_name = await seed_org(app_sessions, github=gh)

    first = await client.get(ORG_MEMBERS, headers=auth_headers(no_app.owner_id, no_app.org_id))
    second = await client.get(ORG_MEMBERS, headers=auth_headers(no_name.owner_id, no_name.org_id))

    assert (first.status_code, second.status_code) == (400, 400)
    assert "not configured" in first.json()["detail"]
    assert "organization name" in second.json()["detail"]
    assert requests_to(gh, "/orgs/") == []
