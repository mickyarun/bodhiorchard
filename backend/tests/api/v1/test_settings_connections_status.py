# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Status-lifecycle tests for ``GET /v1/settings/connections``.

These tests cover the three-state lifecycle the bulk-import flow gates
on:

- ``NOT_CONFIGURED`` — no app_id / no private key.
- ``AWAITING_INSTALL`` — credentials saved, no installation_id yet
  (the user has clicked "Save credentials" but not yet "Install on
  GitHub").
- ``READY`` — installation_id present (the install webhook fired).

The full HTTP+DB integration harness doesn't exist in this repo (no
``client`` / ``db_session`` fixtures live in ``tests/conftest.py`` —
see the conftest docstring for the historical reason). Spinning up a
disposable DB just for this set of pure column→enum projections would
add a lot of scaffolding for no extra coverage. Instead we test the
exact helper the route uses (``_build_github_settings``) against a
plain Organization instance — same code path, no DB required. The
PATCH side-effect (slug fetch) lives in
``tests/services/test_github_app_auth.py``.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.api.v1 import settings as settings_api
from app.api.v1.settings import _build_github_settings, _resolve_github_app_status
from app.models.organization import Organization
from app.schemas.settings import (
    ConnectionsRead,
    ConnectionsUpdate,
    GitHubAppStatus,
    GitHubAppUpdate,
)
from app.services.github_app_slug import (
    ERROR_CODE_INVALID_CREDENTIALS,
    GitHubCredentialsInvalid,
)


def _make_org(
    *,
    app_id: int | None = None,
    private_key: str | None = None,
    installation_id: int | None = None,
    slug: str | None = None,
) -> Organization:
    """Build an unpersisted ``Organization`` with just the GitHub-App
    columns set. ``Organization`` requires ``name`` and ``slug`` for
    its NOT NULL constraints, but we never flush so the values are
    only there to satisfy the constructor's type hints."""
    org = Organization()
    org.name = "Test Org"
    org.slug = "test-org"
    org.github_app_id = app_id
    org.github_app_private_key = private_key
    org.github_app_installation_id = installation_id
    org.github_app_slug = slug
    return org


def test_not_configured_when_credentials_missing() -> None:
    """Empty creds → ``NOT_CONFIGURED``. Boolean ``connected`` must
    track the enum (back-compat with the legacy badge)."""
    org = _make_org()
    assert _resolve_github_app_status(org) == GitHubAppStatus.NOT_CONFIGURED

    settings = _build_github_settings(org)
    assert settings.status == GitHubAppStatus.NOT_CONFIGURED
    assert settings.connected is False
    assert settings.install_url is None
    assert settings.slug is None


def test_awaiting_install_after_creds_saved_with_slug() -> None:
    """Creds + slug + no installation → ``AWAITING_INSTALL`` with a
    fully formed install URL. This is the state the user sees right
    after PATCHing credentials and the slug back-fill succeeding."""
    org = _make_org(
        app_id=12345,
        private_key="encrypted-pem-blob",
        slug="acme-bodhi",
    )
    assert _resolve_github_app_status(org) == GitHubAppStatus.AWAITING_INSTALL

    settings = _build_github_settings(org)
    assert settings.status == GitHubAppStatus.AWAITING_INSTALL
    assert settings.connected is True
    assert settings.slug == "acme-bodhi"
    assert settings.install_url == "https://github.com/apps/acme-bodhi/installations/new"


def test_awaiting_install_without_slug_yields_null_install_url() -> None:
    """If the slug back-fill hasn't landed yet (e.g. GitHub was down
    during PATCH), the status is still ``AWAITING_INSTALL`` but
    ``install_url`` must be None — the frontend then knows to retry
    on the next ``GET /connections``."""
    org = _make_org(app_id=12345, private_key="encrypted-pem-blob")
    settings = _build_github_settings(org)
    assert settings.status == GitHubAppStatus.AWAITING_INSTALL
    assert settings.install_url is None
    assert settings.slug is None


def test_ready_after_installation_id_lands() -> None:
    """Webhook delivers ``installation`` event → ``installation_id`` is
    written → status flips to ``READY``. The Settings card switches
    to the ``Connected`` + ``Installation #N`` badges."""
    org = _make_org(
        app_id=12345,
        private_key="encrypted-pem-blob",
        installation_id=999_888,
        slug="acme-bodhi",
    )
    assert _resolve_github_app_status(org) == GitHubAppStatus.READY

    settings = _build_github_settings(org)
    assert settings.status == GitHubAppStatus.READY
    assert settings.connected is True
    assert settings.installation_id == 999_888
    # Install URL stays populated when slug is known so the user can
    # re-install on additional repos without leaving Settings.
    assert settings.install_url == "https://github.com/apps/acme-bodhi/installations/new"


# ── Phase J: PATCH credential validation ──────────────────────────────


class _FakeOrgRepo:
    """Stand-in for ``OrganizationRepository`` used by the PATCH route.

    Only ``get_for_user`` is invoked by ``update_connections`` directly
    (the strict slug helper uses its own repo instance, which we patch
    separately)."""

    def __init__(self, _db: Any) -> None:
        pass

    @classmethod
    def install(cls, monkeypatch: pytest.MonkeyPatch, org: Organization) -> None:
        """Wire the route's bound name to a stub returning ``org``."""

        async def _get_for_user(_self: Any, _user: Any) -> Organization:
            return org

        monkeypatch.setattr(cls, "get_for_user", _get_for_user, raising=False)
        monkeypatch.setattr(
            settings_api,
            "OrganizationRepository",
            cls,
        )


class _FakeSession:
    """Captures flush/refresh calls; the route helper uses no other
    direct session method."""

    def __init__(self) -> None:
        self.flushed = 0

    async def flush(self) -> None:
        self.flushed += 1

    async def refresh(self, _obj: Any) -> None:
        pass


@pytest.mark.asyncio
async def test_patch_with_bad_credentials_returns_400_typed_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Credential PATCH whose strict validation raises
    ``GitHubCredentialsInvalid`` must surface as HTTP 400 with the
    typed ``github_app_credentials_invalid`` error code so the
    credentials form can render an inline alert.

    The lenient retrofit (``fetch_and_persist_app_slug``) MUST NOT run
    on this path — only the strict validator is in play when the user
    just submitted new credentials."""
    org = Organization()
    org.id = uuid.uuid4()
    org.name = "Test Org"
    org.slug = "test-org"
    org.config = {}
    org.github_app_id = None
    org.github_app_private_key = None
    org.github_app_installation_id = None
    org.github_app_slug = None
    # Slack / Jira columns must exist for ``_build_github_settings``
    # peers but only github is exercised here.

    _FakeOrgRepo.install(monkeypatch, org)

    async def _raise_invalid(_org: Organization, _db: Any) -> str:
        raise GitHubCredentialsInvalid(
            "GitHub rejected the credentials. Check the App ID and private key.",
        )

    lenient_mock = AsyncMock()
    monkeypatch.setattr(settings_api, "validate_and_persist_app_slug", _raise_invalid)
    monkeypatch.setattr(settings_api, "fetch_and_persist_app_slug", lenient_mock)

    body = ConnectionsUpdate(
        github=GitHubAppUpdate(app_id=12345, private_key="-----BEGIN PRIVATE KEY-----")
    )

    with pytest.raises(HTTPException) as excinfo:
        await settings_api.update_connections(
            body=body,
            current_user=object(),  # type: ignore[arg-type]
            db=_FakeSession(),  # type: ignore[arg-type]
        )

    assert excinfo.value.status_code == 400
    detail = excinfo.value.detail
    assert isinstance(detail, dict)
    assert detail["error"] == ERROR_CODE_INVALID_CREDENTIALS
    assert "GitHub rejected" in detail["message"]
    # Lenient retrofit must NOT have been called on the strict path —
    # the strict validator owns the slug fetch when creds are supplied.
    lenient_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_patch_without_new_credentials_uses_lenient_retrofit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When no credential fields appear in the PATCH body but the org
    already has credentials with a null slug, the lenient retrofit
    should still run (back-compat) and the strict validator must NOT
    be called."""
    org = Organization()
    org.id = uuid.uuid4()
    org.name = "Test Org"
    org.slug = "test-org"
    org.config = {}
    org.github_app_id = 12345
    org.github_app_private_key = "encrypted"
    org.github_app_installation_id = None
    org.github_app_slug = None  # missing → eligible for retrofit

    _FakeOrgRepo.install(monkeypatch, org)

    strict_mock = AsyncMock()
    lenient_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(settings_api, "validate_and_persist_app_slug", strict_mock)
    monkeypatch.setattr(settings_api, "fetch_and_persist_app_slug", lenient_mock)

    # Patch out the GET re-fetch at the end of the route — it would try
    # to hit Slack / Jira helpers we don't care about here.
    async def _stub_get(*_args: Any, **_kwargs: Any) -> ConnectionsRead:
        return ConnectionsRead.model_construct()  # type: ignore[call-arg]

    monkeypatch.setattr(settings_api, "get_connections", _stub_get)

    body = ConnectionsUpdate()  # nothing supplied
    await settings_api.update_connections(
        body=body,
        current_user=object(),  # type: ignore[arg-type]
        db=_FakeSession(),  # type: ignore[arg-type]
    )

    strict_mock.assert_not_awaited()
    lenient_mock.assert_awaited_once()


def test_connected_boolean_matches_status_predicate() -> None:
    """Back-compat invariant: ``connected = status != NOT_CONFIGURED``
    for every reachable column combination. Existing
    ``SettingsConnections.vue`` reads ``connected`` and must keep
    rendering identically until it adopts the new enum."""
    cases = [
        _make_org(),  # NOT_CONFIGURED
        _make_org(app_id=1, private_key="x"),  # AWAITING_INSTALL
        _make_org(app_id=1, private_key="x", installation_id=2),  # READY
    ]
    for org in cases:
        settings = _build_github_settings(org)
        assert settings.connected == (settings.status != GitHubAppStatus.NOT_CONFIGURED)
