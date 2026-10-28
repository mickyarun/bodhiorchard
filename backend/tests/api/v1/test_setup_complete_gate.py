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

"""The unauthenticated setup endpoints close once an organization exists.

``init-org``, the legacy ``initialize`` and the Claude/AI connection
checks take no session, because the wizard runs before any user does.
Once an org row exists they must refuse, without provisioning anything
or running a provider check — otherwise anyone on the network could mint
a second org and owner, or use the backend to test stolen API keys.

The DB is replaced by a stub whose only question is "does an org exist?",
and the provisioning and provider calls are replaced by recorders.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI, status
from httpx import ASGITransport, AsyncClient

from app.api.v1 import setup as setup_api
from app.core.auth_deps import get_db

ORG_BODY = {
    "organization": {"name": "Acme", "slug": "acme"},
    "admin": {"email": "owner@acme.dev", "name": "Owner", "password": "correct-horse"},
}
LEGACY_BODY = {**ORG_BODY, "sourceCode": {"repos": [{"path": "/tmp/x"}]}}
GATED = [
    ("post", "/api/setup/init-org", ORG_BODY),
    ("post", "/api/setup/initialize", LEGACY_BODY),
    ("get", "/api/setup/check-claude", None),
    ("post", "/api/setup/check-claude", {"authMode": "api_key", "apiKey": "sk-ant-x"}),
    ("post", "/api/setup/check-ai", {"provider": "claude", "authMode": "host"}),
]


class _Orgs:
    existing: SimpleNamespace | None = None

    def __init__(self, _db: object) -> None:
        pass

    async def check_setup_exists(self) -> SimpleNamespace | None:
        return _Orgs.existing


async def _no_db() -> AsyncIterator[None]:
    yield None


@pytest.fixture
def side_effects(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Names of every provisioning or provider call that ran."""
    ran: list[str] = []

    async def _record(name: str) -> Any:
        ran.append(name)
        raise AssertionError(f"{name} must not run once setup is complete")

    async def _init(*_a: Any, **_k: Any) -> Any:
        return await _record("setup_init_org")

    async def _claude(*_a: Any, **_k: Any) -> Any:
        return await _record("test_claude_connection")

    async def _check(*_a: Any, **_k: Any) -> Any:
        return await _record("check_connection")

    monkeypatch.setattr(_Orgs, "existing", None)
    monkeypatch.setattr(setup_api, "OrganizationRepository", _Orgs)
    monkeypatch.setattr(setup_api, "setup_init_org", _init)
    monkeypatch.setattr(setup_api, "test_claude_connection", _claude)
    monkeypatch.setattr(setup_api, "check_connection", _check)
    return ran


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    app = FastAPI()
    app.include_router(setup_api.router, prefix="/api/setup")
    app.dependency_overrides[get_db] = _no_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield c


async def _call(client: AsyncClient, method: str, url: str, body: object) -> Any:
    if method == "get":
        return await client.get(url)
    return await client.post(url, json=body)


class TestClosedAfterSetup:
    """With an org in place every gated endpoint is a 403 that does nothing."""

    @pytest.mark.parametrize(("method", "url", "body"), GATED)
    async def test_refuses_and_runs_nothing(
        self,
        client: AsyncClient,
        side_effects: list[str],
        method: str,
        url: str,
        body: object,
    ) -> None:
        _Orgs.existing = SimpleNamespace(slug="first-org")
        response = await _call(client, method, url, body)
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "already complete" in response.json()["detail"]
        assert side_effects == []

    async def test_a_second_init_with_a_new_slug_is_still_refused(
        self, client: AsyncClient, side_effects: list[str]
    ) -> None:
        """The gate is "any org exists", not "this slug exists"."""
        _Orgs.existing = SimpleNamespace(slug="first-org")
        body = {**ORG_BODY, "organization": {"name": "Other", "slug": "other-org"}}
        response = await client.post("/api/setup/init-org", json=body)
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert side_effects == []

    async def test_status_reports_the_existing_org(
        self, client: AsyncClient, side_effects: list[str]
    ) -> None:
        _Orgs.existing = SimpleNamespace(slug="first-org")
        response = await client.get("/api/setup/status")
        assert response.json() == {"is_setup_complete": True, "org_slug": "first-org"}


class TestOpenBeforeSetup:
    """Before any org exists the same endpoints validate their input."""

    async def test_status_reports_no_org(
        self, client: AsyncClient, side_effects: list[str]
    ) -> None:
        _Orgs.existing = None
        response = await client.get("/api/setup/status")
        assert response.json() == {"is_setup_complete": False, "org_slug": None}

    @pytest.mark.parametrize(
        ("path", "value"),
        [
            (("organization", "slug"), "Acme Corp"),
            (("organization", "slug"), "-acme"),
            (("organization", "slug"), "a"),
            (("organization", "slug"), "acme_"),
            (("organization", "name"), ""),
            (("admin", "email"), "not-an-email"),
            (("admin", "password"), "short"),
            (("admin", "password"), "x" * 129),
        ],
    )
    async def test_init_org_rejects_bad_input(
        self,
        client: AsyncClient,
        side_effects: list[str],
        path: tuple[str, str],
        value: str,
    ) -> None:
        _Orgs.existing = None
        section, field = path
        body = {**ORG_BODY, section: {**ORG_BODY[section], field: value}}
        response = await client.post("/api/setup/init-org", json=body)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert side_effects == []

    @pytest.mark.parametrize(
        ("body", "detail"),
        [
            ({"authMode": "api_key", "apiKey": "   "}, "api_key is required"),
            ({"authMode": "subscription"}, "oauth_token is required"),
            ({"authMode": "nonsense"}, "auth_mode must be one of"),
        ],
    )
    async def test_check_claude_requires_the_credential_for_its_mode(
        self, client: AsyncClient, side_effects: list[str], body: object, detail: str
    ) -> None:
        _Orgs.existing = None
        response = await client.post("/api/setup/check-claude", json=body)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert detail in response.json()["detail"]
        assert side_effects == []

    async def test_check_ai_rejects_an_unknown_provider(
        self, client: AsyncClient, side_effects: list[str]
    ) -> None:
        _Orgs.existing = None
        response = await client.post(
            "/api/setup/check-ai", json={"provider": "skynet", "authMode": "host"}
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert side_effects == []
