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

"""The GitHub organisation roster for an organisation larger than one API page.

``GET /settings/github/org-members`` used to read a single page of 100
members and never follow GitHub's ``Link: rel="next"``, so everyone past
the hundredth member was missing from the invite flow.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.v1 import settings_github_members
from app.core.encryption import encrypt_secret
from app.core.security import create_access_token
from app.models.organization import Organization
from app.models.user import OrgToUser, User
from app.repositories.role import RoleRepository
from app.services import github_install_repos

pytestmark = pytest.mark.integration
Factory = async_sessionmaker[AsyncSession]
URL = "/api/v1/settings/github/org-members"
PAGE = 100


async def _owner_of_github_org(factory: Factory) -> dict[str, str]:
    """An org owner whose org names the GitHub organisation ``acme``; returns auth headers."""
    tag = uuid.uuid4().hex[:8]
    config = {"integrations": {"github": {"enabled": True, "org": "acme"}}}
    async with factory() as db:
        org = Organization(name=f"Roster {tag}", slug=f"roster-{tag}", config=config)
        org.github_app_id = 7
        org.github_app_private_key = encrypt_secret("unused-key")
        org.github_app_installation_id = 9
        user = User(email=f"owner-{tag}@acme.dev", name="Owner", password_hash="x")
        db.add_all([org, user])
        await db.flush()
        role = await RoleRepository(db).get_by_name_system("org_owner")
        assert role is not None
        db.add(OrgToUser(user_id=user.id, org_id=org.id, role_id=role.id))
        await db.commit()
        token = create_access_token({"sub": str(user.id), "org_id": str(org.id)})
    return {"Authorization": f"Bearer {token}"}


def _github_roster(
    monkeypatch: pytest.MonkeyPatch, logins: list[str], status: int = 200
) -> list[httpx.Request]:
    """Serve ``logins`` 100 per page with ``Link`` headers; return the requests seen."""
    seen: list[httpx.Request] = []

    async def token(org: Organization) -> str:
        return "installation-token"

    async def profile(
        client: httpx.AsyncClient, headers: dict[str, str], login: str
    ) -> dict[str, str | None]:
        return {"name": login, "email": None}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if status != 200:
            return httpx.Response(status, json={"message": "refused"})
        page = int(request.url.params.get("page", "1"))
        chunk = logins[(page - 1) * PAGE : page * PAGE]
        headers = {}
        if page * PAGE < len(logins):
            nxt = request.url.copy_merge_params({"page": str(page + 1)})
            headers["Link"] = f'<{nxt}>; rel="next"'
        return httpx.Response(200, json=[{"login": x} for x in chunk], headers=headers)

    def client(**kwargs: Any) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(settings_github_members, "get_installation_token", token)
    monkeypatch.setattr(settings_github_members, "_fetch_profile", profile)
    monkeypatch.setattr(github_install_repos, "AsyncClient", client)
    # The route's own httpx use goes to the same handler, so no call can leave.
    routed = SimpleNamespace(AsyncClient=client, HTTPStatusError=httpx.HTTPStatusError)
    monkeypatch.setattr(settings_github_members, "httpx", routed)
    return seen


async def test_every_member_comes_back_when_the_roster_spans_pages(
    client: AsyncClient, pg_session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = await _owner_of_github_org(pg_session_factory)
    logins = [f"dev-{n:03d}" for n in range(150)]
    seen = _github_roster(monkeypatch, logins)

    resp = await client.get(URL, headers=headers)

    assert resp.status_code == 200
    assert [m["login"] for m in resp.json()] == logins
    assert [r.url.path for r in seen] == ["/orgs/acme/members"] * 2


async def test_a_refused_roster_is_still_explained(
    client: AsyncClient, pg_session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = await _owner_of_github_org(pg_session_factory)
    _github_roster(monkeypatch, [], status=404)

    resp = await client.get(URL, headers=headers)

    assert resp.status_code == 404
    assert "'acme' not found" in resp.json()["detail"]
