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

"""Changing an org's repositories needs ``settings:edit``.

Clone, bulk import, remove, ignore/activate, branch mapping, classify and
route extraction used to be open to anyone in the engineering workspace, so
a developer could drop or re-point the repos everyone's scans read. Each
route runs through the real router and real system roles here: a developer
gets 403 and an admin gets through. The provider connection test likewise
needs ``integrations:configure``, the same as saving those settings.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest
from httpx import AsyncClient

from app.api.v1 import settings_claude, settings_repos
from app.models.repo_layer import RepoLayer
from app.models.tracked_repository import TrackedRepository
from app.schemas.repo_install import AppInstallState
from tests.integration.leave_support import Factory, as_user, give_role, setup_org

pytestmark = pytest.mark.integration

BASE = "/api/v1/settings"


@pytest.fixture(autouse=True)
def stubs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, Mock]:
    """Stand in for git, GitHub, Redis, the job queue and the model provider.

    The permission check runs before any of these; stubbing them lets the
    admin request finish without touching anything outside the test DB.
    """
    cloned = SimpleNamespace(
        success=True, path=str(tmp_path / "cloned"), error=None, default_branch="main"
    )
    repo_stubs: dict[str, Mock] = {
        "clone_or_update": AsyncMock(return_value=cloned),
        "_detect_develop_branch": AsyncMock(return_value=None),
        "detect_uncommitted_changes": AsyncMock(return_value=False),
        "get_github_repo_full_name": AsyncMock(return_value=None),
        "delete_key": AsyncMock(),
        "resolve_app_install_state": MagicMock(return_value=(AppInstallState.READY, None)),
        "list_installation_repos": AsyncMock(return_value=[SimpleNamespace(full_name="o/web")]),
        "create_job": MagicMock(return_value=SimpleNamespace(job_id="job-1")),
    }
    for name, stub in repo_stubs.items():
        monkeypatch.setattr(settings_repos, name, stub)
    monkeypatch.setattr(settings_claude, "apply_claude_auth_to_env", MagicMock())
    monkeypatch.setattr(
        settings_claude, "check_provider_connection", AsyncMock(return_value={"ok": True})
    )
    return repo_stubs


async def _org(factory: Factory, tmp_path: Path) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """An org with a developer, an admin, and one tracked backend repo."""
    org, (dev, admin), _ = await setup_org(factory, "dev", "admin")
    await give_role(factory, org, dev, "developer")
    await give_role(factory, org, admin, "admin")
    async with factory() as db:
        db.add(
            TrackedRepository(
                org_id=org,
                path=str(tmp_path),
                name="api",
                repo_layer=RepoLayer.BACKEND,
                head_sha="a" * 40,
            )
        )
        await db.commit()
    return org, dev, admin


async def _repo_id(client: AsyncClient, headers: dict[str, str]) -> str:
    listing = await client.get(f"{BASE}/repos", headers=headers)
    assert listing.status_code == 200
    return str(listing.json()[0]["id"])


Request = tuple[str, str, dict[str, object] | None]


def _requests(repo_id: str, path: str) -> dict[str, Request]:
    """Every repository-changing request by label, as (method, url, json body)."""
    bulk_item = {"fullName": "o/web", "mainBranch": "main"}
    return {
        "clone": ("POST", f"{BASE}/repos/clone", {"url": "https://github.com/o/web.git"}),
        "bulk-onboard": ("POST", f"{BASE}/repos/bulk-onboard", {"items": [bulk_item]}),
        "status": ("PATCH", f"{BASE}/repos/{repo_id}/status", {"status": "ignored"}),
        "branches": ("PATCH", f"{BASE}/repos/{repo_id}/branches", {"mainBranch": "trunk"}),
        "classify": ("POST", f"{BASE}/repos/{repo_id}/classify", None),
        "extract-routes": ("POST", f"{BASE}/repos/{repo_id}/extract-routes", None),
        "claude-test": ("POST", f"{BASE}/claude/test", None),
        # Last: it removes the repo the other requests act on.
        "remove": ("DELETE", f"{BASE}/repos", {"path": path}),
    }


LABELS = list(_requests("id", "path"))


@pytest.mark.parametrize("label", LABELS)
async def test_a_developer_cannot_change_repositories(
    client: AsyncClient,
    pg_session_factory: Factory,
    tmp_path: Path,
    stubs: dict[str, Mock],
    label: str,
) -> None:
    org, dev, _ = await _org(pg_session_factory, tmp_path)
    headers = as_user(dev, org)
    repo_id = await _repo_id(client, headers)

    method, url, body = _requests(repo_id, str(tmp_path))[label]
    response = await client.request(method, url, json=body, headers=headers)

    assert response.status_code == 403, response.text
    # Nothing changed: the repo is still tracked, active, on its old branches.
    after = (await client.get(f"{BASE}/repos", headers=headers)).json()
    assert [(r["id"], r["status"], r["mainBranch"]) for r in after] == [(repo_id, "active", None)]
    for stub in stubs.values():
        assert not stub.called


async def test_an_admin_can_change_repositories(
    client: AsyncClient, pg_session_factory: Factory, tmp_path: Path
) -> None:
    org, _, admin = await _org(pg_session_factory, tmp_path)
    headers = as_user(admin, org)
    repo_id = await _repo_id(client, headers)

    for method, url, body in _requests(repo_id, str(tmp_path)).values():
        response = await client.request(method, url, json=body, headers=headers)
        assert 200 <= response.status_code < 300, (method, url, response.text)
