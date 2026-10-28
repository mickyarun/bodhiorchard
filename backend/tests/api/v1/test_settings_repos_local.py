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

"""The local-checkout picker endpoints have two independent guards.

``browse-directories`` and ``local-branches`` take a caller-chosen
filesystem path, so they are confined twice over:

* **by caller**: a session plus ``settings:edit``, enforced once on the
  router — no token is a 401, a member without the permission a 403.
* **in space**, by ``picker_roots``: the resolved path must stay under the
  home directory, so the picker walks checkouts rather than the host.

Guards with no tests are guards that get deleted, so each is asserted in
both directions — refusing what it should, and still serving the setup
wizard and Settings → Code, which is the case they exist to permit.

Requests go through a real ASGI app so the router-level dependency runs;
only the user and permission lookups are stubbed, since the repo has no
HTTP+DB fixture (see ``tests/conftest.py``).
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

from app.api.v1 import settings_repos_local as local_api
from app.config import settings as app_settings
from app.core.auth_deps import get_current_user, get_db
from app.core.permission_deps import PermissionSet, get_permission_set

BROWSE = "/api/v1/settings/repos/browse-directories"
BRANCHES = "/api/v1/settings/repos/local-branches"


async def _no_db() -> AsyncIterator[None]:
    yield None


def _app(permissions: frozenset[str] | None) -> FastAPI:
    """The router at its production prefix; ``None`` means no session."""
    app = FastAPI()
    app.include_router(local_api.router, prefix="/api/v1/settings")
    app.dependency_overrides[get_db] = _no_db
    if permissions is not None:
        user = SimpleNamespace(id=uuid.uuid4(), must_change_password=False)
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_permission_set] = lambda: PermissionSet(
            ids=permissions, is_owner=False
        )
    return app


@pytest.fixture
async def anonymous() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=_app(None)), base_url="http://t") as c:
        yield c


@pytest.fixture
async def viewer() -> AsyncIterator[AsyncClient]:
    """Signed in, but only ``settings:view`` — like the developer role."""
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
    """Point the allowed root at a temp directory, not the real home.

    ``tmp_path`` sits outside ``$HOME``, so without this every call in this
    module would be refused for the wrong reason — and the alternative,
    writing fixtures into the developer's actual home directory, is worse.
    """
    root = tmp_path / "home"
    root.mkdir()
    monkeypatch.setattr(local_api, "picker_roots", lambda: (root,))
    return root


def _git(*args: str, cwd: Path) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
    )


@pytest.fixture
def checkout(picker_root: Path, tmp_path: Path) -> Iterator[Path]:
    """A real clone under the root, with ``main`` and ``develop`` on origin."""
    origin = tmp_path / "origin.git"
    _git("init", "--bare", "-b", "main", str(origin), cwd=tmp_path)
    repo = picker_root / "taskflow"
    _git("clone", str(origin), str(repo), cwd=tmp_path)
    _git("commit", "--allow-empty", "-m", "init", cwd=repo)
    _git("push", "origin", "HEAD:main", "HEAD:develop", cwd=repo)
    _git("fetch", "origin", cwd=repo)
    yield repo


class TestNeedsAnEditorSession:
    """The caller guard: runs before anything touches the filesystem."""

    @pytest.mark.parametrize("url", [BROWSE, BRANCHES])
    async def test_no_token_is_401(
        self, anonymous: AsyncClient, picker_root: Path, url: str
    ) -> None:
        response = await anonymous.get(url, params={"path": str(picker_root)})
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.parametrize("url", [BROWSE, BRANCHES])
    async def test_without_settings_edit_is_403(
        self, viewer: AsyncClient, picker_root: Path, url: str
    ) -> None:
        response = await viewer.get(url, params={"path": str(picker_root)})
        assert response.status_code == status.HTTP_403_FORBIDDEN


class TestConfinedToTheRoots:
    """The space guard: nothing outside the allowed roots, by any route."""

    @pytest.mark.parametrize("url", [BROWSE, BRANCHES])
    async def test_refuses_a_path_outside(
        self, editor: AsyncClient, picker_root: Path, url: str
    ) -> None:
        response = await editor.get(url, params={"path": "/etc"})
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "outside" in response.json()["detail"]

    @pytest.mark.parametrize("url", [BROWSE, BRANCHES])
    async def test_refuses_traversal_out_of_a_root(
        self, editor: AsyncClient, picker_root: Path, url: str
    ) -> None:
        """``..`` is collapsed before the check, so it cannot climb out."""
        response = await editor.get(url, params={"path": f"{picker_root}/../../.."})
        assert response.status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.parametrize("url", [BROWSE, BRANCHES])
    async def test_refuses_a_symlink_escape(
        self, editor: AsyncClient, picker_root: Path, url: str
    ) -> None:
        """realpath follows the link, so a link out of the root is caught."""
        escape = picker_root / "escape"
        escape.symlink_to("/etc")
        response = await editor.get(url, params={"path": str(escape)})
        assert response.status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.parametrize("url", [BROWSE, BRANCHES])
    @pytest.mark.parametrize("spelling", ["repos", "REPOS"])
    async def test_refuses_the_clone_root_under_a_root(
        self,
        editor: AsyncClient,
        picker_root: Path,
        monkeypatch: pytest.MonkeyPatch,
        url: str,
        spelling: str,
    ) -> None:
        """A host install keeps every org's clones under home; none are listable.

        The upper-case spelling is what a case-insensitive disk (macOS) still
        opens, so it must be refused the same way.
        """
        data_dir = picker_root / "code" / "app" / ".data"
        monkeypatch.setattr(app_settings.storage, "data_dir", str(data_dir))
        (app_settings.storage.repos_dir / "other-org" / "billing").mkdir(parents=True)

        target = data_dir / spelling / "other-org" / "billing"
        response = await editor.get(url, params={"path": str(target)})

        assert response.status_code == status.HTTP_403_FORBIDDEN


class TestServesThePicker:
    """Neither guard may break the case they exist to allow."""

    async def test_browse_lists_directories_and_flags_repos(
        self, editor: AsyncClient, checkout: Path, picker_root: Path
    ) -> None:
        (picker_root / "notes").mkdir()
        (picker_root / "readme.txt").write_text("not a directory")

        response = await editor.get(BROWSE, params={"path": str(picker_root)})

        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert body["current_path"] == str(picker_root.resolve())
        assert [(d["name"], d["is_git_repo"]) for d in body["directories"]] == [
            ("notes", False),
            ("taskflow", True),
        ]

    async def test_local_branches_reads_a_real_checkout(
        self, editor: AsyncClient, checkout: Path
    ) -> None:
        response = await editor.get(BRANCHES, params={"path": str(checkout)})

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {
            "branches": ["develop", "main"],
            "detectedMain": "main",
            "detectedDevelop": "develop",
        }

    async def test_local_branches_of_an_onboarded_checkout_with_no_remote(
        self, editor: AsyncClient, picker_root: Path
    ) -> None:
        """No remote, and develop checked out in a worktree as onboarding does."""
        repo = picker_root / "local-only"
        repo.mkdir()
        _git("init", "-q", "-b", "main", cwd=repo)
        _git("commit", "-q", "--allow-empty", "-m", "init", cwd=repo)
        _git("branch", "develop", cwd=repo)
        _git("worktree", "add", "-q", str(repo / ".bodhiorchard" / "develop"), "develop", cwd=repo)

        response = await editor.get(BRANCHES, params={"path": str(repo)})

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {
            "branches": ["develop", "main"],
            "detectedMain": "main",
            "detectedDevelop": "develop",
        }

    async def test_local_branches_rejects_a_folder_that_is_not_a_repo(
        self, editor: AsyncClient, picker_root: Path
    ) -> None:
        """The wizard shows this 400 inline instead of adding a dead entry."""
        (picker_root / "zip-download").mkdir()
        response = await editor.get(BRANCHES, params={"path": str(picker_root / "zip-download")})
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.json()["detail"].startswith("Not a git repository")

    def test_the_default_root_is_the_home_directory(self) -> None:
        """The shipped root, which the fixture above deliberately replaces."""
        assert local_api.picker_roots() == (Path.home(),)
