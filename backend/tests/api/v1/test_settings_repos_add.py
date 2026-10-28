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

"""Adding a repository by path is held to the same bar as the picker.

``POST /api/v1/settings/repos`` registers a caller-chosen filesystem path
for the org and then runs git against it, so it carries both guards of
the folder picker that feeds it (``test_settings_repos_local.py``):

* **by caller**: a session plus ``settings:edit`` — no token is a 401, a
  member without the permission a 403.
* **in space**, by ``picker_roots``: the resolved path must stay under the
  home directory, and never under the backend's clone root, which holds
  every org's clones side by side.

Requests go through a real ASGI app so the route dependency runs; the
user and permission lookups are stubbed, and so are the two repositories
the handler writes through, since the repo has no HTTP+DB fixture (see
``tests/conftest.py``). Git itself runs for real against a temp clone.
"""

from __future__ import annotations

import subprocess
import uuid
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, status
from httpx import ASGITransport, AsyncClient

from app.api.v1 import settings_repos as repos_api
from app.config import settings as app_settings
from app.core.auth_deps import get_current_user, get_db
from app.core.permission_deps import PermissionSet, get_permission_set
from app.models.tracked_repository import RepoStatus, TrackedRepository

ADD = "/api/v1/settings/repos"


class _Session:
    """Just enough of an ``AsyncSession`` for the handler's final flush."""

    async def flush(self) -> None:
        return None


class _Orgs:
    def __init__(self, _db: object) -> None:
        pass

    async def get_for_user(self, _user: object) -> SimpleNamespace:
        return SimpleNamespace(id=uuid.uuid4())


class _TrackedRepos:
    """Records what the handler registers, so tests can assert on it."""

    registered: list[str] = []

    def __init__(self, _db: object, *, org_id: uuid.UUID) -> None:
        self._org_id = org_id

    async def upsert(self, path: str, name: str) -> TrackedRepository:
        _TrackedRepos.registered.append(path)
        return TrackedRepository(
            id=uuid.uuid4(),
            org_id=self._org_id,
            path=path,
            name=name,
            status=RepoStatus.ACTIVE,
            knowledge_count=0,
            feature_count=0,
        )


async def _session() -> AsyncIterator[_Session]:
    yield _Session()


def _app(permissions: frozenset[str] | None) -> FastAPI:
    """The router at its production prefix; ``None`` means no session."""
    app = FastAPI()
    app.include_router(repos_api.router, prefix="/api/v1/settings")
    app.dependency_overrides[get_db] = _session
    if permissions is not None:
        user = SimpleNamespace(id=uuid.uuid4(), must_change_password=False)
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_permission_set] = lambda: PermissionSet(
            ids=permissions, is_owner=False
        )
    return app


@pytest.fixture(autouse=True)
def stub_repositories(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[str]]:
    _TrackedRepos.registered = []
    monkeypatch.setattr(repos_api, "OrganizationRepository", _Orgs)
    monkeypatch.setattr(repos_api, "TrackedRepoRepository", _TrackedRepos)
    yield _TrackedRepos.registered


@pytest.fixture
async def anonymous() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=_app(None)), base_url="http://t") as c:
        yield c


@pytest.fixture
async def viewer() -> AsyncIterator[AsyncClient]:
    """Signed in, but only ``settings:view`` — like the developer and QA roles."""
    app = _app(frozenset({"settings:view"}))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield c


@pytest.fixture
async def editor() -> AsyncIterator[AsyncClient]:
    app = _app(frozenset({"settings:view", "settings:edit"}))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield c


@pytest.fixture
def picker_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Point the allowed root at a temp directory, not the real home."""
    root = tmp_path / "home"
    root.mkdir()
    monkeypatch.setattr(repos_api, "picker_roots", lambda: (root,))
    return root


def _git(*args: str, cwd: Path) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
    )


def _checkout(parent: Path, name: str, tmp_path: Path) -> Path:
    """A real clone with ``main`` and ``develop`` on origin."""
    origin = tmp_path / f"{name}-origin.git"
    _git("init", "--bare", "-b", "main", str(origin), cwd=tmp_path)
    repo = parent / name
    _git("clone", str(origin), str(repo), cwd=tmp_path)
    _git("commit", "--allow-empty", "-m", "init", cwd=repo)
    _git("push", "origin", "HEAD:main", "HEAD:develop", cwd=repo)
    _git("fetch", "origin", cwd=repo)
    return repo


class TestNeedsAnEditorSession:
    """The caller guard: runs before anything touches the filesystem."""

    async def test_no_token_is_401(self, anonymous: AsyncClient, picker_root: Path) -> None:
        response = await anonymous.post(ADD, json={"path": str(picker_root)})
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_without_settings_edit_is_403(
        self, viewer: AsyncClient, picker_root: Path, tmp_path: Path, stub_repositories: list[str]
    ) -> None:
        repo = _checkout(picker_root, "taskflow", tmp_path)
        response = await viewer.post(ADD, json={"path": str(repo)})
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert stub_repositories == []


class TestConfinedToTheRoots:
    """The space guard: nothing outside the allowed roots is registered."""

    async def test_refuses_a_checkout_outside(
        self, editor: AsyncClient, picker_root: Path, tmp_path: Path, stub_repositories: list[str]
    ) -> None:
        outside = _checkout(tmp_path, "elsewhere", tmp_path)
        response = await editor.post(ADD, json={"path": str(outside)})
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "outside" in response.json()["detail"]
        assert stub_repositories == []

    async def test_refuses_traversal_out_of_a_root(
        self, editor: AsyncClient, picker_root: Path, tmp_path: Path, stub_repositories: list[str]
    ) -> None:
        """``..`` is collapsed before the check, so it cannot climb out."""
        _checkout(tmp_path, "elsewhere", tmp_path)
        response = await editor.post(ADD, json={"path": f"{picker_root}/../elsewhere"})
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert stub_repositories == []

    async def test_refuses_a_symlink_escape(
        self, editor: AsyncClient, picker_root: Path, tmp_path: Path, stub_repositories: list[str]
    ) -> None:
        """realpath follows the link, so a link out of the root is caught."""
        outside = _checkout(tmp_path, "elsewhere", tmp_path)
        (picker_root / "escape").symlink_to(outside)
        response = await editor.post(ADD, json={"path": str(picker_root / "escape")})
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert stub_repositories == []

    async def test_refuses_another_orgs_clone_under_a_root(
        self,
        editor: AsyncClient,
        picker_root: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        stub_repositories: list[str],
    ) -> None:
        """A host install keeps its clone root in the checkout, so under home.

        Clones are registered by ``/repos/clone``, and the clone root holds
        every org's clones side by side — so it is refused even here.
        """
        data_dir = picker_root / "code" / "bodhiorchard" / "backend" / ".data"
        monkeypatch.setattr(app_settings.storage, "data_dir", str(data_dir))
        org_clones = app_settings.storage.repos_dir / "other-org"
        org_clones.mkdir(parents=True)
        cloned = _checkout(org_clones, "billing", tmp_path)

        response = await editor.post(ADD, json={"path": str(cloned)})

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert stub_repositories == []


class TestStillAddsUnderARoot:
    """Neither guard may break the case they exist to allow."""

    async def test_refuses_the_clone_root_spelled_in_another_case(
        self,
        editor: AsyncClient,
        picker_root: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        stub_repositories: list[str],
    ) -> None:
        """On a case-insensitive disk ``REPOS`` opens ``repos``; it is refused all the same."""
        data_dir = picker_root / "code" / "bodhiorchard" / "backend" / ".data"
        monkeypatch.setattr(app_settings.storage, "data_dir", str(data_dir))
        org_clones = app_settings.storage.repos_dir / "other-org"
        org_clones.mkdir(parents=True)
        _checkout(org_clones, "billing", tmp_path)

        response = await editor.post(ADD, json={"path": str(data_dir / "REPOS/other-org/billing")})

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert stub_repositories == []

    async def test_registers_a_checkout_under_a_root(
        self, editor: AsyncClient, picker_root: Path, tmp_path: Path, stub_repositories: list[str]
    ) -> None:
        repo = _checkout(picker_root, "taskflow", tmp_path)

        response = await editor.post(ADD, json={"path": str(repo)})

        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert body["name"] == "taskflow"
        assert body["mainBranch"] == "main"
        assert body["developBranch"] == "develop"
        assert stub_repositories == [str(repo.resolve())]

    async def test_a_folder_that_is_not_a_repo_is_still_a_400(
        self, editor: AsyncClient, picker_root: Path, stub_repositories: list[str]
    ) -> None:
        (picker_root / "zip-download").mkdir()
        response = await editor.post(ADD, json={"path": str(picker_root / "zip-download")})
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.json()["detail"].startswith("Path is not a git repository")
        assert stub_repositories == []
