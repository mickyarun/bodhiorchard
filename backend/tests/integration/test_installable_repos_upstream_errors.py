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

"""The repo picker routes when GitHub refuses the installation's API calls.

A rate-limited or refused ``/installation/repositories`` call used to
escape ``GET /settings/repos/installable`` (and the branch and bulk-onboard
routes) as an unhandled ``httpx.HTTPStatusError``: a bare 500 the picker
could only show as a generic failure.
"""

from __future__ import annotations

import uuid
from typing import Any

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.v1._github_upstream import NO_ACCESS, RATE_LIMITED, UNAVAILABLE
from app.core.encryption import encrypt_secret
from app.core.security import create_access_token
from app.models.organization import Organization
from app.models.user import OrgToUser, User
from app.repositories.role import RoleRepository
from app.services import github_install_repos, redis_client

pytestmark = pytest.mark.integration
Factory = async_sessionmaker[AsyncSession]
BASE = "/api/v1/settings/repos"
RATE_LIMIT_HEADERS = {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "4102444800"}


async def _installed_owner(factory: Factory) -> dict[str, str]:
    """An org owner whose org has a fully installed GitHub App; returns auth headers."""
    tag = uuid.uuid4().hex[:8]
    async with factory() as db:
        org = Organization(name=f"Picker {tag}", slug=f"picker-{tag}", config={})
        org.github_app_id = 7
        org.github_app_private_key = encrypt_secret("unused-key")
        org.github_app_installation_id = 9
        org.github_app_slug = "picker-app"
        user = User(email=f"owner-{tag}@acme.dev", name="Owner", password_hash="x")
        db.add_all([org, user])
        await db.flush()
        role = await RoleRepository(db).get_by_name_system("org_owner")
        assert role is not None
        db.add(OrgToUser(user_id=user.id, org_id=org.id, role_id=role.id))
        await db.commit()
        token = create_access_token({"sub": str(user.id), "org_id": str(org.id)})
    return {"Authorization": f"Bearer {token}"}


def _github_answers(
    monkeypatch: pytest.MonkeyPatch, status: int, headers: dict[str, str] | None = None
) -> None:
    """Every GitHub listing call answers ``status``; the token exchange is skipped."""

    async def token(org: Organization) -> str:
        return "installation-token"

    def handler(request: httpx.Request) -> httpx.Response:
        if status != 200:
            return httpx.Response(status, json={"message": "refused"}, headers=headers or {})
        repo = {"full_name": "acme/shop", "owner": {"login": "acme"}, "id": 1}
        return httpx.Response(200, json={"total_count": 1, "repositories": [repo]})

    def client(**kwargs: Any) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(github_install_repos, "get_installation_token", token)
    monkeypatch.setattr(github_install_repos, "AsyncClient", client)
    monkeypatch.setattr(redis_client, "_redis", None)
    monkeypatch.setattr(redis_client, "_redis_available", False)


@pytest.mark.parametrize(
    ("github_status", "headers", "status", "detail"),
    [
        (403, RATE_LIMIT_HEADERS, 429, RATE_LIMITED),
        (429, None, 429, RATE_LIMITED),
        (403, None, 400, NO_ACCESS),
        (401, None, 400, NO_ACCESS),
        (500, None, 502, UNAVAILABLE),
    ],
)
async def test_the_picker_explains_a_refused_repo_listing(
    github_status: int,
    headers: dict[str, str] | None,
    status: int,
    detail: str,
    client: AsyncClient,
    pg_session_factory: Factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    auth = await _installed_owner(pg_session_factory)
    _github_answers(monkeypatch, github_status, headers)

    resp = await client.get(f"{BASE}/installable", headers=auth)

    assert (resp.status_code, resp.json()["detail"]) == (status, detail)


@pytest.mark.parametrize("route", ["branches", "bulk_onboard"])
async def test_the_branch_and_onboard_routes_explain_a_rate_limit_too(
    route: str, client: AsyncClient, pg_session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth = await _installed_owner(pg_session_factory)
    _github_answers(monkeypatch, 403, RATE_LIMIT_HEADERS)

    if route == "branches":
        resp = await client.get(f"{BASE}/installable/acme/shop/branches", headers=auth)
    else:
        items = [{"fullName": "acme/shop", "mainBranch": "main"}]
        resp = await client.post(f"{BASE}/bulk-onboard", json={"items": items}, headers=auth)

    assert (resp.status_code, resp.json()["detail"]) == (429, RATE_LIMITED)


async def test_the_picker_still_lists_repos_when_github_answers(
    client: AsyncClient, pg_session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth = await _installed_owner(pg_session_factory)
    _github_answers(monkeypatch, 200)

    resp = await client.get(f"{BASE}/installable", headers=auth)

    assert resp.status_code == 200
    assert [r["fullName"] for r in resp.json()["repos"]] == ["acme/shop"]
