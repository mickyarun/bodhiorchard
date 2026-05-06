# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Tests for the two-stage wizard split (Phase D).

The full HTTP+DB harness doesn't live in this repo (see
``tests/conftest.py`` for the historical reason), so these tests
exercise the service-level helpers directly with the SQLAlchemy /
GitHub / job-queue layers stubbed out — same pattern as
``tests/services/test_job_repo_bulk_clone.py``.

Coverage:

- ``setup_init_org`` — happy path and Claude-auth XOR.
- ``setup_finalize_with_repos`` legacy path — kicks the sync scan.
- ``setup_finalize_with_repos`` App path — enqueues the async job.
- ``setup_finalize_with_repos`` App path — 409 when the App isn't READY.
- ``FinalizeWithReposRequest`` — XOR validator catches both/neither.
- The deprecated ``initialize_setup`` shim still composes the two
  helpers and returns the legacy ``SetupResponse`` shape.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from pydantic import ValidationError

from app.api.v1 import setup as setup_api
from app.schemas.repo_install import AppInstallState, BulkOnboardItem
from app.schemas.setup import (
    FinalizeWithReposRequest,
    InitOrgRequest,
    SetupAdmin,
    SetupClaude,
    SetupOrganization,
    SetupRepo,
    SetupRequest,
    SetupSourceCode,
)
from app.services import setup_finalize, setup_finalize_legacy, setup_init

# ── Test doubles ───────────────────────────────────────────────────


class _FakeOrg:
    """Stand-in for ``Organization`` — only the fields the helpers read."""

    def __init__(
        self,
        *,
        slug: str = "acme",
        github_app_id: int | None = 1,
        github_app_private_key: str | None = "pem",
        github_app_installation_id: int | None = 99,
        github_app_slug: str | None = "acme-bodhi",
        **kwargs: Any,
    ) -> None:
        self.id: uuid.UUID = uuid.uuid4()
        self.slug = kwargs.get("slug", slug)
        self.name = kwargs.get("name", "Acme")
        self.config = kwargs.get("config", {})
        self.mcp_token_hash = kwargs.get("mcp_token_hash")
        self.claude_auth_mode = kwargs.get("claude_auth_mode", "host")
        self.claude_api_key_encrypted = kwargs.get("claude_api_key_encrypted")
        self.github_app_id = github_app_id
        self.github_app_private_key = github_app_private_key
        self.github_app_installation_id = github_app_installation_id
        self.github_app_slug = github_app_slug


class _FakeUser:
    def __init__(self, **kwargs: Any) -> None:
        self.id: uuid.UUID = uuid.uuid4()
        self.email = kwargs.get("email", "admin@acme.com")
        self.name = kwargs.get("name", "Admin")
        self.password_hash = kwargs.get("password_hash", "x")


class _FakeOrgRepo:
    """Replaces ``OrganizationRepository``."""

    existing: _FakeOrg | None = None

    def __init__(self, _db: Any) -> None:
        pass

    async def get_by_slug(self, _slug: str) -> _FakeOrg | None:
        return _FakeOrgRepo.existing


class _FakeRoleRepo:
    def __init__(self, _db: Any) -> None:
        pass

    async def get_by_name_system(self, _name: str) -> Any:
        class _Role:
            id = uuid.uuid4()

        return _Role()


class _FakeSession:
    """No-op session — flush / commit / refresh do nothing."""

    def __init__(self) -> None:
        self.added: list[Any] = []

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        return None

    async def refresh(self, _obj: Any) -> None:
        return None


# ── Fixtures ───────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_state() -> None:
    _FakeOrgRepo.existing = None


@pytest.fixture
def patched_init(monkeypatch: pytest.MonkeyPatch) -> None:
    """Wire test doubles into ``setup_init``."""
    monkeypatch.setattr(setup_init, "OrganizationRepository", _FakeOrgRepo)
    monkeypatch.setattr(setup_init, "RoleRepository", _FakeRoleRepo)

    async def _seed_perms(_db: Any) -> None:
        return None

    async def _seed_skills(_org_id: uuid.UUID, _db: Any) -> None:
        return None

    async def _seed_stages(_org_id: uuid.UUID, _db: Any) -> None:
        return None

    monkeypatch.setattr(setup_init, "seed_permissions", _seed_perms)
    monkeypatch.setattr(setup_init, "seed_skills_for_org", _seed_skills)
    monkeypatch.setattr(setup_init, "seed_stage_mappings_for_org", _seed_stages)
    monkeypatch.setattr(setup_init, "apply_claude_auth_to_env", lambda _org: None)
    # The Organization / User constructors hit SQLAlchemy machinery; swap them
    # for plain stand-ins so the test session never touches the ORM.
    monkeypatch.setattr(setup_init, "Organization", _FakeOrg)
    monkeypatch.setattr(setup_init, "User", _FakeUser)

    class _StubMembership:
        def __init__(self, **_kwargs: Any) -> None:
            pass

    monkeypatch.setattr(setup_init, "OrgToUser", _StubMembership)
    monkeypatch.setattr(setup_init, "create_access_token", lambda data: f"jwt-{data['sub']}")
    monkeypatch.setattr(setup_init, "hash_password", lambda pw: f"hash:{pw}")
    monkeypatch.setattr(setup_init, "encrypt_secret", lambda v: f"enc:{v}")


def _make_init_req(slug: str = "acme") -> InitOrgRequest:
    return InitOrgRequest(
        organization=SetupOrganization(name="Acme", slug=slug),
        admin=SetupAdmin(email="admin@acme.com", name="Admin", password="password123"),
        claude=SetupClaude(auth_mode="host"),
    )


# ── Tests: setup_init_org ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_setup_init_org_creates_org_and_returns_jwt(patched_init: None) -> None:
    """Happy path — org+user+role+JWT all materialise."""
    db = _FakeSession()
    result = await setup_init.setup_init_org(_make_init_req(), db)  # type: ignore[arg-type]

    assert result.org.slug == "acme"
    assert result.access_token.startswith("jwt-")
    assert result.mcp_token  # cleartext returned for the wizard


@pytest.mark.asyncio
async def test_setup_init_org_rejects_bad_claude_auth(patched_init: None) -> None:
    """Invalid ``claude.auth_mode`` is a 400."""
    req = InitOrgRequest(
        organization=SetupOrganization(name="A", slug="acme"),
        admin=SetupAdmin(email="a@b.com", name="A", password="password123"),
        claude=SetupClaude(auth_mode="not-a-mode"),
    )
    db = _FakeSession()
    with pytest.raises(Exception) as exc:  # noqa: PT011 - HTTPException
        await setup_init.setup_init_org(req, db)  # type: ignore[arg-type]
    assert "auth_mode" in str(exc.value)


# ── Tests: FinalizeWithReposRequest XOR ───────────────────────────


def test_finalize_rejects_both_payloads_or_neither() -> None:
    """The model_validator must reject both-or-neither payloads."""
    item = BulkOnboardItem(full_name="acme/widgets", main_branch="main")
    src = SetupSourceCode(repos=[SetupRepo(path="/tmp/repo")])

    with pytest.raises(ValidationError):
        FinalizeWithReposRequest(installable_items=None, source_code=None)
    with pytest.raises(ValidationError):
        FinalizeWithReposRequest(installable_items=[item], source_code=src)


# ── Tests: setup_finalize_with_repos ──────────────────────────────


@pytest.mark.asyncio
async def test_finalize_legacy_path_kicks_scan(monkeypatch: pytest.MonkeyPatch) -> None:
    """Legacy path delegates to the legacy helper and returns the scan_id."""
    captured: dict[str, Any] = {}

    async def _fake_legacy(*, org: Any, source_code: Any, db: Any) -> Any:
        captured["org"] = org
        captured["source_code"] = source_code
        return setup_finalize_legacy.LegacyFinalizeResult(
            scan_id="scan-123",
            embedding_warning=None,
        )

    monkeypatch.setattr(setup_finalize, "finalize_legacy_source_code", _fake_legacy)

    req = FinalizeWithReposRequest(
        installable_items=None,
        source_code=SetupSourceCode(repos=[SetupRepo(path="/tmp/repo")]),
    )
    org = _FakeOrg()
    user = _FakeUser()
    db = _FakeSession()
    resp = await setup_finalize.setup_finalize_with_repos(
        org=org,  # type: ignore[arg-type]
        user=user,  # type: ignore[arg-type]
        req=req,
        db=db,  # type: ignore[arg-type]
    )

    assert resp.scan_id == "scan-123"
    assert resp.job_id is None
    assert resp.is_setup_complete is True
    assert captured["org"] is org


@pytest.mark.asyncio
async def test_finalize_app_path_enqueues_job(monkeypatch: pytest.MonkeyPatch) -> None:
    """App path enqueues a JOB_REPO_BULK_ONBOARD job with the items shape."""
    fake_org = _FakeOrg()
    fake_user = _FakeUser()
    payloads: list[dict[str, Any]] = []

    async def _fake_list(_org: Any, _db: Any) -> list[Any]:
        class _R:
            full_name = "acme/widgets"

        return [_R()]

    def _fake_resolve(_org: Any) -> tuple[Any, str | None]:
        return AppInstallState.READY, "https://github.com/apps/acme-bodhi/installations/new"

    def _fake_is_active(_job_type: str, _match: dict[str, str]) -> bool:
        return False

    class _FakeJob:
        job_id = "job-abc"

    def _fake_create_job(job_type: str, *, payload: dict[str, Any], user_id: str) -> _FakeJob:
        payloads.append({"job_type": job_type, "payload": payload, "user_id": user_id})
        return _FakeJob()

    monkeypatch.setattr(setup_finalize, "list_installation_repos", _fake_list)
    monkeypatch.setattr(setup_finalize, "resolve_app_install_state", _fake_resolve)
    monkeypatch.setattr(setup_finalize, "is_job_active", _fake_is_active)
    monkeypatch.setattr(setup_finalize, "create_job", _fake_create_job)

    req = FinalizeWithReposRequest(
        installable_items=[BulkOnboardItem(full_name="acme/widgets", main_branch="main")],
        source_code=None,
    )
    db = _FakeSession()
    resp = await setup_finalize.setup_finalize_with_repos(
        org=fake_org,  # type: ignore[arg-type]
        user=fake_user,  # type: ignore[arg-type]
        req=req,
        db=db,  # type: ignore[arg-type]
    )

    assert resp.job_id == "job-abc"
    assert resp.scan_id is None
    assert len(payloads) == 1
    assert payloads[0]["job_type"] == "repo_bulk_onboard"
    items = payloads[0]["payload"]["items"]
    assert items[0]["full_name"] == "acme/widgets"
    assert items[0]["main_branch"] == "main"
    assert items[0]["status"] == "pending"


@pytest.mark.asyncio
async def test_finalize_app_path_rejects_unready_app(monkeypatch: pytest.MonkeyPatch) -> None:
    """409 when the GitHub-App installation isn't READY yet."""

    def _fake_resolve(_org: Any) -> tuple[Any, str | None]:
        return AppInstallState.NO_INSTALL, None

    monkeypatch.setattr(setup_finalize, "resolve_app_install_state", _fake_resolve)

    req = FinalizeWithReposRequest(
        installable_items=[BulkOnboardItem(full_name="acme/widgets", main_branch="main")],
        source_code=None,
    )
    org = _FakeOrg(github_app_installation_id=None)
    user = _FakeUser()
    db = _FakeSession()
    with pytest.raises(Exception) as exc:  # noqa: PT011 - HTTPException
        await setup_finalize.setup_finalize_with_repos(
            org=org,  # type: ignore[arg-type]
            user=user,  # type: ignore[arg-type]
            req=req,
            db=db,  # type: ignore[arg-type]
        )
    assert "not ready" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_finalize_app_path_rejects_unknown_full_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """400 when the picker submitted a repo not in the installation set."""

    async def _fake_list(_org: Any, _db: Any) -> list[Any]:
        return []

    def _fake_resolve(_org: Any) -> tuple[Any, str | None]:
        return AppInstallState.READY, None

    monkeypatch.setattr(setup_finalize, "list_installation_repos", _fake_list)
    monkeypatch.setattr(setup_finalize, "resolve_app_install_state", _fake_resolve)

    req = FinalizeWithReposRequest(
        installable_items=[BulkOnboardItem(full_name="acme/ghost", main_branch="main")],
        source_code=None,
    )
    org = _FakeOrg()
    user = _FakeUser()
    db = _FakeSession()
    with pytest.raises(Exception) as exc:  # noqa: PT011 - HTTPException
        await setup_finalize.setup_finalize_with_repos(
            org=org,  # type: ignore[arg-type]
            user=user,  # type: ignore[arg-type]
            req=req,
            db=db,  # type: ignore[arg-type]
        )
    assert "not in installation set" in str(exc.value).lower()


# ── Tests: deprecated /setup/initialize shim ──────────────────────


@pytest.mark.asyncio
async def test_initialize_shim_still_works(
    monkeypatch: pytest.MonkeyPatch,
    patched_init: None,
) -> None:
    """The deprecated single-shot endpoint still composes init + finalize.

    Calls the api-layer handler directly to verify the legacy
    ``SetupResponse`` shape is preserved (org_id + scan_id + JWT).
    """

    async def _fake_legacy(*, org: Any, source_code: Any, db: Any) -> Any:
        return setup_finalize_legacy.LegacyFinalizeResult(
            scan_id="scan-shim-1",
            embedding_warning=None,
        )

    monkeypatch.setattr(setup_finalize, "finalize_legacy_source_code", _fake_legacy)

    # The shim's reload step calls OrganizationRepository.get_by_slug to fetch
    # the just-created org. Make _FakeOrgRepo return a fake org for that call.
    fake_org = _FakeOrg(slug="acme-shim")
    _FakeOrgRepo.existing = None  # First check (in setup_init_org) — must be None.
    call_count = {"n": 0}

    async def _toggling_get_by_slug(self: Any, _slug: str) -> _FakeOrg | None:
        call_count["n"] += 1
        # Stage-1 sees an empty DB; the shim's reload-after-init sees the new org.
        return None if call_count["n"] == 1 else fake_org

    monkeypatch.setattr(_FakeOrgRepo, "get_by_slug", _toggling_get_by_slug)
    monkeypatch.setattr(setup_api, "OrganizationRepository", _FakeOrgRepo)

    async def _no_gate(_db: Any) -> None:
        return None

    monkeypatch.setattr(setup_api, "_require_setup_incomplete", _no_gate)

    body = SetupRequest(
        organization=SetupOrganization(name="Acme", slug="acme-shim"),
        admin=SetupAdmin(email="a@b.com", name="A", password="password123"),
        sourceCode=SetupSourceCode(repos=[SetupRepo(path="/tmp/repo")]),
        claude=SetupClaude(auth_mode="host"),
    )
    db = _FakeSession()
    resp = await setup_api.initialize_setup(body=body, db=db)  # type: ignore[arg-type]

    assert resp.scan_id == "scan-shim-1"
    assert resp.access_token.startswith("jwt-")
    assert resp.organization_id  # populated from the freshly-created org
