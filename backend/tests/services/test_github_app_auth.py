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

"""Tests for GitHub App auth — focused on the slug back-fill path.

The slug is what builds ``https://github.com/apps/{slug}/installations/new``,
so it has to land on the org row the first time we have credentials. Two
entry points back-fill it:

- ``fetch_and_persist_app_slug`` — request-time, in
  ``PATCH /v1/settings/connections``.
- ``spawn_slug_retrofit`` — fire-and-forget, on the first successful
  ``get_installation_token`` call.

These tests cover the request-time helper end-to-end with a mocked GitHub
``GET /app`` and an in-memory fake of the small repository surface the
helper touches. The token-fetch retrofit shares the same
``_fetch_app_slug`` primitive, so we don't duplicate the HTTP mocking
there — the null-check guard in ``get_installation_token`` is exercised
by inspection of ``spawn_slug_retrofit`` being called once.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
import respx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import Response

from app.core.encryption import encrypt_secret
from app.services.github_app_jwt import GITHUB_APP_ENDPOINT
from app.services.github_app_slug import (
    GitHubAppNotFound,
    GitHubCredentialsInvalid,
    GitHubUnreachable,
    fetch_and_persist_app_slug,
    validate_and_persist_app_slug,
)


def _generate_rsa_pem() -> str:
    """Return a fresh RSA private key in PKCS#8 PEM (the format ``jwt``
    accepts for RS256). Generated per-test so we never embed a key in
    the repo."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return pem.decode("utf-8")


class _FakeOrg:
    """Stand-in for ``app.models.organization.Organization``.

    The slug helper only reads/writes a handful of columns and never
    triggers ORM lazy loads. A plain object with the right attributes
    is enough — and avoids spinning up the full SQLAlchemy machinery
    for what is otherwise a pure-function test.
    """

    def __init__(self, app_id: int, encrypted_pk: str) -> None:
        self.id: uuid.UUID = uuid.uuid4()
        self.github_app_id: int | None = app_id
        self.github_app_private_key: str | None = encrypted_pk
        self.github_app_installation_id: int | None = None
        self.github_app_slug: str | None = None


class _FakeSession:
    """Captures ``flush`` / ``refresh`` calls; the helper uses no other
    session method directly. SQL writes go through the repository,
    which we patch out separately."""

    def __init__(self) -> None:
        self.flushed: int = 0
        self.refreshed: list[Any] = []

    async def flush(self) -> None:
        self.flushed += 1

    async def refresh(self, obj: Any) -> None:
        self.refreshed.append(obj)


class _CapturingRepo:
    """Minimal stand-in for ``OrganizationRepository`` — records the
    persisted slug so the assertion is on observable state, not on the
    DB."""

    persisted: dict[uuid.UUID, str] = {}

    def __init__(self, _db: Any) -> None:
        pass

    async def update_app_slug(self, org_id: uuid.UUID, slug: str) -> None:
        type(self).persisted[org_id] = slug


@pytest.fixture(autouse=True)
def _reset_repo_state() -> None:
    """Clear the captured-slug map between tests so they stay isolated."""
    _CapturingRepo.persisted = {}


@pytest.mark.asyncio
@respx.mock
async def test_slug_backfill(monkeypatch: pytest.MonkeyPatch) -> None:
    """Happy path: org has creds + null slug → ``GET /app`` is called →
    slug is persisted on the org and through the repository."""
    pem = _generate_rsa_pem()
    org = _FakeOrg(app_id=12345, encrypted_pk=encrypt_secret(pem))

    # Patch the repository so we don't need a real DB. The helper
    # imports the symbol at module scope, so we patch the bound name.
    monkeypatch.setattr(
        "app.services.github_app_slug.OrganizationRepository",
        _CapturingRepo,
    )

    route = respx.get(GITHUB_APP_ENDPOINT).mock(
        return_value=Response(200, json={"slug": "acme-bodhi", "name": "Acme Bodhi"})
    )

    session = _FakeSession()
    result = await fetch_and_persist_app_slug(org, session)  # type: ignore[arg-type]

    assert result == "acme-bodhi"
    assert org.github_app_slug == "acme-bodhi"
    assert _CapturingRepo.persisted[org.id] == "acme-bodhi"
    assert route.called
    # MissingGreenlet guard: helper must flush + refresh after the
    # repo write so subsequent attribute reads on ``org`` are safe.
    assert session.flushed == 1
    assert session.refreshed == [org]


@pytest.mark.asyncio
@respx.mock
async def test_slug_backfill_swallows_github_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 5xx from GitHub must NOT bubble up — settings PATCH must keep
    succeeding even if the slug fetch fails. The org's slug stays null
    so the next call retries."""
    pem = _generate_rsa_pem()
    org = _FakeOrg(app_id=12345, encrypted_pk=encrypt_secret(pem))

    monkeypatch.setattr(
        "app.services.github_app_slug.OrganizationRepository",
        _CapturingRepo,
    )

    respx.get(GITHUB_APP_ENDPOINT).mock(return_value=Response(503))

    session = _FakeSession()
    result = await fetch_and_persist_app_slug(org, session)  # type: ignore[arg-type]

    assert result is None
    assert org.github_app_slug is None
    assert _CapturingRepo.persisted == {}
    assert session.flushed == 0


@pytest.mark.asyncio
async def test_slug_backfill_skips_when_credentials_missing() -> None:
    """No app_id or no private key → return None without HTTP. Guards
    the helper from accidentally signing a JWT with empty creds."""
    org = _FakeOrg(app_id=0, encrypted_pk="")
    org.github_app_id = None

    session = _FakeSession()
    result = await fetch_and_persist_app_slug(org, session)  # type: ignore[arg-type]

    assert result is None
    assert session.flushed == 0


# ── Phase J: synchronous credential validation ────────────────────────


@pytest.mark.asyncio
@respx.mock
async def test_validate_raises_on_401_invalid_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GitHub returns 401 → typed ``GitHubCredentialsInvalid``.

    The route handler maps this to HTTP 400 with the
    ``github_app_credentials_invalid`` error code so the credentials
    form can render an inline alert."""
    pem = _generate_rsa_pem()
    org = _FakeOrg(app_id=12345, encrypted_pk=encrypt_secret(pem))
    monkeypatch.setattr(
        "app.services.github_app_slug.OrganizationRepository",
        _CapturingRepo,
    )
    respx.get(GITHUB_APP_ENDPOINT).mock(return_value=Response(401))

    session = _FakeSession()
    with pytest.raises(GitHubCredentialsInvalid):
        await validate_and_persist_app_slug(org, session)  # type: ignore[arg-type]
    assert org.github_app_slug is None
    assert _CapturingRepo.persisted == {}


@pytest.mark.asyncio
@respx.mock
async def test_validate_raises_on_404_app_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """404 → typed ``GitHubAppNotFound`` (wrong App ID)."""
    pem = _generate_rsa_pem()
    org = _FakeOrg(app_id=12345, encrypted_pk=encrypt_secret(pem))
    monkeypatch.setattr(
        "app.services.github_app_slug.OrganizationRepository",
        _CapturingRepo,
    )
    respx.get(GITHUB_APP_ENDPOINT).mock(return_value=Response(404))

    session = _FakeSession()
    with pytest.raises(GitHubAppNotFound):
        await validate_and_persist_app_slug(org, session)  # type: ignore[arg-type]
    assert _CapturingRepo.persisted == {}


@pytest.mark.asyncio
@respx.mock
async def test_validate_raises_on_network_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Connection error → typed ``GitHubUnreachable``."""
    import httpx

    pem = _generate_rsa_pem()
    org = _FakeOrg(app_id=12345, encrypted_pk=encrypt_secret(pem))
    monkeypatch.setattr(
        "app.services.github_app_slug.OrganizationRepository",
        _CapturingRepo,
    )
    respx.get(GITHUB_APP_ENDPOINT).mock(side_effect=httpx.ConnectError("dns boom"))

    session = _FakeSession()
    with pytest.raises(GitHubUnreachable):
        await validate_and_persist_app_slug(org, session)  # type: ignore[arg-type]


@pytest.mark.asyncio
@respx.mock
async def test_validate_persists_slug_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """Happy path: 200 + slug → returns slug and persists on the org."""
    pem = _generate_rsa_pem()
    org = _FakeOrg(app_id=12345, encrypted_pk=encrypt_secret(pem))
    monkeypatch.setattr(
        "app.services.github_app_slug.OrganizationRepository",
        _CapturingRepo,
    )
    respx.get(GITHUB_APP_ENDPOINT).mock(
        return_value=Response(200, json={"slug": "acme-bodhi", "name": "Acme Bodhi"})
    )

    session = _FakeSession()
    slug = await validate_and_persist_app_slug(org, session)  # type: ignore[arg-type]

    assert slug == "acme-bodhi"
    assert org.github_app_slug == "acme-bodhi"
    assert _CapturingRepo.persisted[org.id] == "acme-bodhi"
    assert session.flushed == 1
