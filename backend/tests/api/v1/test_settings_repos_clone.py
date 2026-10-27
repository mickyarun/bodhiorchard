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

"""A GitHub clone hands the setup wizard its branches in the clone response.

In Full Docker the clone lands under ``/data/repos``, outside the
local-checkout picker's roots, so the wizard cannot read a cloned repo's
branches by path — ``local-branches`` refuses it, and the dropdown used
to blank when it did. The wizard therefore takes main *and* develop from
``POST /repos/clone``. These tests pin both halves: the clone response
carries the detected branches, and the clone root stays outside the
picker, which serves one org's checkouts rather than every org's clones.

Requests go through a real ASGI app against a real git clone; only the
org and tracked-repo lookups are stubbed, since the repo has no HTTP+DB
fixture (see ``tests/conftest.py``).
"""

from __future__ import annotations

import subprocess
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, status
from httpx import ASGITransport, AsyncClient

from app.api.v1 import settings_repos as repos_api
from app.api.v1 import settings_repos_local as local_api
from app.core.auth_deps import get_current_user, get_db
from app.core.permission_deps import PermissionSet, get_permission_set
from app.models.tracked_repository import RepoStatus, TrackedRepository
from app.services.repo_cloner import CloneResult

CLONE = "/api/v1/settings/repos/clone"
BRANCHES = "/api/v1/settings/repos/local-branches"
ORG_SLUG = "acme"


def _git(*args: str, cwd: Path) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
    )


@pytest.fixture
def cloned(tmp_path: Path) -> Path:
    """A real clone where the Docker clone root puts one, origin on main + develop."""
    origin = tmp_path / "origin.git"
    _git("init", "--bare", "-b", "main", str(origin), cwd=tmp_path)
    dest = tmp_path / "data" / "repos" / ORG_SLUG / "taskflow"
    dest.parent.mkdir(parents=True)
    _git("clone", str(origin), str(dest), cwd=tmp_path)
    _git("commit", "--allow-empty", "-m", "init", cwd=dest)
    _git("push", "origin", "HEAD:main", "HEAD:develop", cwd=dest)
    _git("fetch", "origin", cwd=dest)
    return dest


class _FakeDb:
    async def flush(self) -> None:
        return None


class _FakeOrgRepo:
    def __init__(self, _db: object) -> None:
        pass

    async def get_for_user(self, _user: object) -> SimpleNamespace:
        return SimpleNamespace(id=uuid.uuid4(), slug=ORG_SLUG)


class _FakeTrackedRepoRepo:
    def __init__(self, _db: object, *, org_id: uuid.UUID) -> None:
        self._org_id = org_id

    async def upsert(self, path: str, name: str) -> TrackedRepository:
        return TrackedRepository(
            id=uuid.uuid4(),
            org_id=self._org_id,
            path=path,
            name=name,
            status=RepoStatus.ACTIVE,
            knowledge_count=0,
            feature_count=0,
        )


@pytest.fixture
async def client(monkeypatch: pytest.MonkeyPatch, cloned: Path) -> AsyncIterator[AsyncClient]:
    """Both settings routers at their production prefix, signed in as an editor."""

    async def _clone(_url: str, **_kwargs: object) -> CloneResult:
        return CloneResult(success=True, path=str(cloned), default_branch="main")

    async def _db() -> AsyncIterator[_FakeDb]:
        yield _FakeDb()

    monkeypatch.setattr(repos_api, "clone_or_update", _clone)
    monkeypatch.setattr(repos_api, "OrganizationRepository", _FakeOrgRepo)
    monkeypatch.setattr(repos_api, "TrackedRepoRepository", _FakeTrackedRepoRepo)

    app = FastAPI()
    app.include_router(repos_api.router, prefix="/api/v1/settings")
    app.include_router(local_api.router, prefix="/api/v1/settings")
    user = SimpleNamespace(id=uuid.uuid4(), must_change_password=False)
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_permission_set] = lambda: PermissionSet(
        ids=frozenset({"settings:view", "settings:edit"}), is_owner=False
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield c


async def test_clone_response_carries_main_and_develop(client: AsyncClient) -> None:
    """The wizard reads both branches from here instead of a path lookup."""
    response = await client.post(CLONE, json={"url": "https://github.com/acme/taskflow"})

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["mainBranch"] == "main"
    assert body["developBranch"] == "develop"


async def test_a_clone_is_outside_the_picker_roots(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, cloned: Path, tmp_path: Path
) -> None:
    """Why the wizard must not look a clone up by path: the picker refuses it.

    The picker root is the home directory and the clone root a sibling of
    it, as in Full Docker (``/home/appuser`` vs ``/data/repos``). Widening
    the roots to the clone root would let one org list every org's clones.
    """
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(local_api, "picker_roots", lambda: (home,))

    response = await client.get(BRANCHES, params={"path": str(cloned)})

    assert response.status_code == status.HTTP_403_FORBIDDEN
