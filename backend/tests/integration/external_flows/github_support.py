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

"""Shared setup for the GitHub App flows: org state and request helpers."""

from __future__ import annotations

import itertools
import re
import uuid

import httpx
from sqlalchemy.orm.attributes import flag_modified

from app.models.organization import Organization
from app.models.user import User
from app.repositories.organization import OrganizationRepository
from tests.fakes.github import API_HOST, FakeGitHub
from tests.fakes.http_router import FakeHttpRouter
from tests.fakes.seed import Factory

INSTALLABLE = "/api/v1/settings/repos/installable"
BULK_ONBOARD = "/api/v1/settings/repos/bulk-onboard"
ORG_MEMBERS = "/api/v1/settings/github/org-members"
CONNECTIONS = "/api/v1/settings/connections"


_APP_IDS = itertools.count(500_001)


def fresh_app_id() -> int:
    """A GitHub App id no other org in this test session uses."""
    return next(_APP_IDS)


def unique_name(prefix: str = "svc") -> str:
    """A repo name no other test uses (webhook routing is cross-org)."""
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


async def load_org(factory: Factory, org_id: uuid.UUID) -> Organization:
    """The org row as it is now."""
    async with factory() as db:
        org = await OrganizationRepository(db).get_by_id(org_id)
        assert org is not None
        return org


async def update_org(factory: Factory, org_id: uuid.UUID, **columns: object) -> None:
    """Set plain columns on the org row (``github_app_slug=None`` …)."""
    async with factory() as db:
        org = await db.get(Organization, org_id)
        assert org is not None
        for name, value in columns.items():
            setattr(org, name, value)
        await db.commit()


async def set_installation(factory: Factory, org_id: uuid.UUID, install_id: int | None) -> None:
    """Pretend the install webhook has (or has not) fired yet."""
    await update_org(factory, org_id, github_app_installation_id=install_id)


async def set_github_org(factory: Factory, org_id: uuid.UUID, login: str) -> None:
    """Store the GitHub organisation name the members endpoint reads."""
    async with factory() as db:
        org = await db.get(Organization, org_id)
        assert org is not None
        config = dict(org.config or {})
        config["integrations"] = {"github": {"enabled": True, "org": login}}
        org.config = config
        flag_modified(org, "config")
        await db.commit()


async def set_github_username(factory: Factory, user_id: uuid.UUID, login: str) -> None:
    """Record ``login`` as the member's GitHub account."""
    async with factory() as db:
        user = await db.get(User, user_id)
        assert user is not None
        user.github_username = login
        await db.commit()


async def drop_app_credentials(factory: Factory, org_id: uuid.UUID) -> None:
    """Remove the App id and key, as for an org that never set the App up."""
    await update_org(factory, org_id, github_app_id=None, github_app_private_key=None)


def bearer_tokens(github: FakeGitHub, path_part: str) -> list[str]:
    """The bearer token of every request the fake saw whose path contains ``path_part``."""
    return [
        r.headers.get("authorization", "").removeprefix("Bearer ")
        for r in github.requests
        if path_part in r.url.path
    ]


def requests_to(github: FakeGitHub, path_part: str) -> list[httpx.Request]:
    """Requests the fake saw whose path contains ``path_part``."""
    return [r for r in github.requests if path_part in r.url.path]


def page_org_members(router: FakeHttpRouter, github: FakeGitHub) -> None:
    """Serve ``/orgs/{org}/members`` a page at a time, with ``Link``, as GitHub does.

    The shared fake answers the member list in one response; this override
    (mounted over it for ``api.github.com``) pages it like every other list
    and hands every other request to the fake.
    """

    def handle(request: httpx.Request) -> httpx.Response:
        if not re.fullmatch(r"/orgs/[^/]+/members", request.url.path):
            return github.handle(request)
        github.requests.append(request)
        token = request.headers.get("authorization", "").removeprefix("Bearer ")
        if token not in github.issued_tokens:
            return httpx.Response(401, json={"message": "Bad credentials"})
        items = [{"login": login, "avatar_url": ""} for login in github.members]
        return github.page(request, items, None)

    router.mount(API_HOST, handle)
