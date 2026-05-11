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

"""Tests for the install-event branch of the GitHub webhook handler.

Covers Phase L bug-fix: ``installation`` and ``installation_repositories``
deliveries carry no top-level ``repository``, so the original handler
short-circuited before persisting the install_id. The new path resolves
the org by ``installation.app_id`` and writes
``Organization.github_app_installation_id`` end-to-end.

The full HTTP+DB integration harness doesn't exist in this repo (see
``tests/conftest.py`` for the historical reason). We test the dedicated
helper ``_handle_install_event`` directly with in-memory fakes — same
code path the FastAPI route invokes, no DB required.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.api.v1 import github_webhook as gh_webhook
from app.api.v1.github_webhook import (
    ACTION_CREATED,
    ACTION_DELETED,
    EVENT_INSTALLATION,
    _apply_install_state,
    _handle_install_event,
)

_FAKE_PLAINTEXT_SECRET = "s3cret-webhook-token"
_ENCRYPTED_MARKER = "enc::s3cret-webhook-token"


def _sign(body: bytes, secret: str = _FAKE_PLAINTEXT_SECRET) -> str:
    """Reproduce GitHub's ``X-Hub-Signature-256`` header for ``body``."""
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


class _FakeOrg:
    """Minimal stand-in for ``Organization`` covering only the columns
    the install-event branch reads or mutates."""

    def __init__(
        self,
        *,
        app_id: int = 12345,
        installation_id: int | None = None,
        webhook_secret: str | None = _ENCRYPTED_MARKER,
    ) -> None:
        self.id: uuid.UUID = uuid.uuid4()
        self.github_app_id: int | None = app_id
        self.github_app_installation_id: int | None = installation_id
        self.github_webhook_secret: str | None = webhook_secret


class _FakeSession:
    """Captures ``flush`` / ``commit`` calls; the install branch uses no
    other session method directly. SQL writes go through repositories
    which are patched out separately."""

    def __init__(self) -> None:
        self.flushed: int = 0
        self.committed: int = 0

    async def flush(self) -> None:
        self.flushed += 1

    async def commit(self) -> None:
        self.committed += 1


class _FakeOrgRepo:
    """Resolves a single pre-seeded org by ``app_id`` and returns None
    for any other ID — matches the new repository contract."""

    def __init__(self, db: Any, *, org: _FakeOrg | None = None) -> None:
        self._org = org

    async def get_by_github_app_id(self, app_id: int) -> _FakeOrg | None:
        if self._org is None:
            return None
        return self._org if self._org.github_app_id == app_id else None


class _FakeWebhookLogRepo:
    """Tracks recorded deliveries so we can assert idempotency."""

    seen: set[str] = set()

    def __init__(self, db: Any, *, org_id: uuid.UUID) -> None:
        self._org_id = org_id

    async def record_delivery(
        self,
        *,
        delivery_id: str,
        event_type: str,
        org_id: uuid.UUID,
        payload_summary: dict[str, Any] | None = None,
    ) -> bool:
        cls = type(self)
        if delivery_id in cls.seen:
            return False
        cls.seen.add(delivery_id)
        return True


@pytest.fixture(autouse=True)
def _reset_log_state() -> None:
    """Clear delivery-id memory between tests."""
    _FakeWebhookLogRepo.seen = set()


def _patch_module(
    monkeypatch: pytest.MonkeyPatch,
    *,
    org: _FakeOrg | None,
) -> _FakeSession:
    """Wire fakes into the webhook module so ``_handle_install_event``
    runs end-to-end without touching the database or encryption."""
    session = _FakeSession()

    @asynccontextmanager
    async def _session_cm() -> Any:
        yield session

    monkeypatch.setattr(
        gh_webhook,
        "AsyncSessionLocal",
        lambda: _session_cm(),
    )

    def _org_repo_factory(db: Any) -> _FakeOrgRepo:
        return _FakeOrgRepo(db, org=org)

    monkeypatch.setattr(gh_webhook, "OrganizationRepository", _org_repo_factory)
    monkeypatch.setattr(gh_webhook, "WebhookLogRepository", _FakeWebhookLogRepo)
    monkeypatch.setattr(
        gh_webhook,
        "decrypt_secret",
        lambda s: _FAKE_PLAINTEXT_SECRET if s == _ENCRYPTED_MARKER else "",
    )
    return session


def _install_payload(
    *,
    app_id: int = 12345,
    installation_id: int = 99999,
    action: str = ACTION_CREATED,
) -> bytes:
    payload = {
        "action": action,
        "installation": {
            "id": installation_id,
            "app_id": app_id,
            "account": {"login": "acme"},
        },
    }
    return json.dumps(payload).encode()


@pytest.mark.asyncio
async def test_installation_created_persists_install_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Happy path: ``installation.created`` → install_id written, 200 OK,
    delivery recorded, session committed."""
    org = _FakeOrg(installation_id=None)
    session = _patch_module(monkeypatch, org=org)

    body = _install_payload(installation_id=42)
    response = await _handle_install_event(
        body=body,
        signature=_sign(body),
        event_type=EVENT_INSTALLATION,
        delivery_id="delivery-1",
        payload=json.loads(body),
    )

    assert response.status_code == 200
    assert org.github_app_installation_id == 42
    assert session.committed == 1
    assert "delivery-1" in _FakeWebhookLogRepo.seen


@pytest.mark.asyncio
async def test_installation_created_bad_signature_returns_401(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tampered signature → 401, no DB mutation, no delivery record."""
    org = _FakeOrg(installation_id=None)
    session = _patch_module(monkeypatch, org=org)

    body = _install_payload()
    response = await _handle_install_event(
        body=body,
        signature="sha256=deadbeef",
        event_type=EVENT_INSTALLATION,
        delivery_id="delivery-bad-sig",
        payload=json.loads(body),
    )

    assert response.status_code == 401
    assert org.github_app_installation_id is None
    assert session.committed == 0
    assert "delivery-bad-sig" not in _FakeWebhookLogRepo.seen


@pytest.mark.asyncio
async def test_installation_created_no_matching_org_returns_200(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unknown ``app_id`` → 200 OK, no DB write. Cross-org webhook noise
    must never escalate to a 4xx (GitHub would keep retrying)."""
    session = _patch_module(monkeypatch, org=None)

    body = _install_payload(app_id=99999)
    response = await _handle_install_event(
        body=body,
        signature=_sign(body),
        event_type=EVENT_INSTALLATION,
        delivery_id="delivery-no-match",
        payload=json.loads(body),
    )

    assert response.status_code == 200
    assert session.committed == 0
    assert _FakeWebhookLogRepo.seen == set()


@pytest.mark.asyncio
async def test_installation_duplicate_delivery_short_circuits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Replay of the same delivery_id → 200 ``{"status":"duplicate"}`` and
    no second mutation. Idempotency mirrors the repo-scoped path."""
    org = _FakeOrg(installation_id=None)
    session = _patch_module(monkeypatch, org=org)

    body = _install_payload(installation_id=42)
    sig = _sign(body)
    payload = json.loads(body)

    first = await _handle_install_event(
        body=body,
        signature=sig,
        event_type=EVENT_INSTALLATION,
        delivery_id="dup-1",
        payload=payload,
    )
    assert first.status_code == 200
    assert org.github_app_installation_id == 42
    assert session.committed == 1

    # Second delivery: install_id already set, dedupe must prevent any
    # extra commit / state churn.
    second = await _handle_install_event(
        body=body,
        signature=sig,
        event_type=EVENT_INSTALLATION,
        delivery_id="dup-1",
        payload=payload,
    )
    assert second.status_code == 200
    assert json.loads(second.body) == {"status": "duplicate"}
    assert session.committed == 1


@pytest.mark.asyncio
async def test_installation_deleted_clears_install_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``installation.deleted`` → install_id back to None, log recorded."""
    org = _FakeOrg(installation_id=42)
    _patch_module(monkeypatch, org=org)

    body = _install_payload(installation_id=42, action=ACTION_DELETED)
    response = await _handle_install_event(
        body=body,
        signature=_sign(body),
        event_type=EVENT_INSTALLATION,
        delivery_id="delivery-delete",
        payload=json.loads(body),
    )

    assert response.status_code == 200
    assert org.github_app_installation_id is None


# ── direct unit tests for _apply_install_state ────────────────────────


@pytest.mark.asyncio
async def test_apply_install_state_overwrites_changed_install_id() -> None:
    """Re-install with a new installation_id must overwrite the old one."""
    org = _FakeOrg(installation_id=10)
    session = _FakeSession()
    org_typed: Any = org

    await _apply_install_state(
        db=session,  # type: ignore[arg-type]
        org=org_typed,
        event_type=EVENT_INSTALLATION,
        action=ACTION_CREATED,
        install_id=99,
    )

    assert org.github_app_installation_id == 99
    assert session.flushed == 1


@pytest.mark.asyncio
async def test_apply_install_state_skips_when_unchanged() -> None:
    """Idempotent re-set must be a no-op (no flush)."""
    org = _FakeOrg(installation_id=42)
    session = _FakeSession()
    org_typed: Any = org

    await _apply_install_state(
        db=session,  # type: ignore[arg-type]
        org=org_typed,
        event_type=EVENT_INSTALLATION,
        action=ACTION_CREATED,
        install_id=42,
    )

    assert org.github_app_installation_id == 42
    assert session.flushed == 0


# unused imports kept for readability of the test surface
_ = AsyncMock
