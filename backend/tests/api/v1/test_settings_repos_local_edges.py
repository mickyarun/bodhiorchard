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

"""The folder picker's corner cases, beyond the guards in the main suite.

``test_settings_repos_local.py`` pins the session and root guards. This
module covers what the picker does with awkward input that still passes
them, or nearly does: ``~``, a sibling that shares the root's prefix, a
symlink that stays inside, missing paths, files, unreadable folders,
unicode names, and what the listing hides.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from fastapi import status
from httpx import ASGITransport, AsyncClient

from app.api.v1 import settings_repos_local as local_api
from tests.api.v1.repo_path_support import init_repo, run_git, settings_app

BROWSE = "/api/v1/settings/repos/browse-directories"
BRANCHES = "/api/v1/settings/repos/local-branches"


async def _no_db() -> AsyncIterator[None]:
    yield None


@pytest.fixture
async def editor() -> AsyncIterator[AsyncClient]:
    app = settings_app(local_api.router, _no_db)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield c


@pytest.fixture
def root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """The only picker root, under ``tmp_path`` and fully resolved."""
    path = (tmp_path / "home").resolve()
    path.mkdir()
    monkeypatch.setattr(local_api, "picker_roots", lambda: (path,))
    return path


@pytest.fixture
def locked(root: Path) -> Iterator[Path]:
    """A folder under the root that its owner cannot read."""
    path = root / "locked"
    path.mkdir()
    path.chmod(0)
    yield path
    path.chmod(0o755)


async def _names(client: AsyncClient, path: Path | str) -> list[str]:
    response = await client.get(BROWSE, params={"path": str(path)})
    assert response.status_code == status.HTTP_200_OK, response.text
    return [d["name"] for d in response.json()["directories"]]


class TestBrowseRefusals:
    """Inputs that pass the root guard but cannot be listed."""

    async def test_missing_folder_is_404(self, editor: AsyncClient, root: Path) -> None:
        response = await editor.get(BROWSE, params={"path": str(root / "gone")})
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "does not exist" in response.json()["detail"]

    async def test_a_file_is_400(self, editor: AsyncClient, root: Path) -> None:
        (root / "notes.txt").write_text("x")
        response = await editor.get(BROWSE, params={"path": str(root / "notes.txt")})
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "not a directory" in response.json()["detail"]

    @pytest.mark.skipif(os.geteuid() == 0, reason="root reads any folder")
    async def test_an_unreadable_folder_is_403(self, editor: AsyncClient, locked: Path) -> None:
        response = await editor.get(BROWSE, params={"path": str(locked)})
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "Permission denied" in response.json()["detail"]

    async def test_a_sibling_sharing_the_roots_prefix_is_refused(
        self, editor: AsyncClient, root: Path
    ) -> None:
        """``home2`` starts with ``home`` but is not under it."""
        sibling = root.parent / f"{root.name}2"
        sibling.mkdir()
        response = await editor.get(BROWSE, params={"path": str(sibling)})
        assert response.status_code == status.HTTP_403_FORBIDDEN

    async def test_a_relative_path_resolves_against_the_process_not_the_root(
        self, editor: AsyncClient, root: Path
    ) -> None:
        (root / "projects").mkdir()
        response = await editor.get(BROWSE, params={"path": "projects"})
        assert response.status_code == status.HTTP_403_FORBIDDEN


class TestHomeShorthand:
    """``~`` and the empty default both mean the server user's home."""

    async def test_tilde_lists_home_when_home_is_a_root(
        self, editor: AsyncClient, root: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("HOME", str(root))
        (root / "code").mkdir()
        response = await editor.get(BROWSE, params={"path": "~/code/.."})
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["current_path"] == str(root)

    async def test_empty_path_defaults_to_home(
        self, editor: AsyncClient, root: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("HOME", str(root))
        response = await editor.get(BROWSE)
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["current_path"] == str(root)

    async def test_tilde_outside_the_roots_is_refused(
        self, editor: AsyncClient, root: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        monkeypatch.setenv("HOME", str(elsewhere))
        for path in ("~", ""):
            response = await editor.get(BROWSE, params={"path": path})
            assert response.status_code == status.HTTP_403_FORBIDDEN


class TestListing:
    """What the picker shows of a folder it may list."""

    async def test_hides_dotfolders_and_files_and_sorts(
        self, editor: AsyncClient, root: Path
    ) -> None:
        for name in ("zeta", ".cache", "alpha", "Mid"):
            (root / name).mkdir()
        (root / "readme.md").write_text("x")
        assert await _names(editor, root) == ["Mid", "alpha", "zeta"]

    async def test_lists_unicode_names(self, editor: AsyncClient, root: Path) -> None:
        names = {"café", "日本語-repo", "emoji-🚀"}
        for name in names:
            (root / name).mkdir()
        assert set(await _names(editor, root)) == names

    async def test_flags_a_monorepo_but_not_a_plain_repo(
        self, editor: AsyncClient, root: Path
    ) -> None:
        init_repo(root / "mono")
        init_repo(root / "mono" / "services" / "api")
        init_repo(root / "mono" / "web")
        init_repo(root / "single")
        response = await editor.get(BROWSE, params={"path": str(root)})
        flags = {
            d["name"]: (d["is_git_repo"], d["has_sub_repos"])
            for d in response.json()["directories"]
        }
        # Only one level down is peeked: services/api alone would not count.
        assert flags == {"mono": (True, True), "single": (True, False)}

    async def test_parent_of_a_subfolder_is_reported(
        self, editor: AsyncClient, root: Path
    ) -> None:
        (root / "code" / "inner").mkdir(parents=True)
        body = (await editor.get(BROWSE, params={"path": str(root / "code")})).json()
        assert body["parent_path"] == str(root)
        assert body["directories"][0]["path"] == str(root / "code" / "inner")

    async def test_a_symlink_that_stays_inside_lists_its_target(
        self, editor: AsyncClient, root: Path
    ) -> None:
        (root / "real" / "child").mkdir(parents=True)
        (root / "shortcut").symlink_to(root / "real")
        body = (await editor.get(BROWSE, params={"path": str(root / "shortcut")})).json()
        assert body["current_path"] == str(root / "real")
        assert [d["name"] for d in body["directories"]] == ["child"]


class TestBranchLookupRefusals:
    """``local-branches`` doubles as the wizard's "is this a repo?" check."""

    @pytest.mark.parametrize("name", ["gone", "notes.txt", "plain"])
    async def test_not_a_checkout_is_400(self, editor: AsyncClient, root: Path, name: str) -> None:
        (root / "notes.txt").write_text("x")
        (root / "plain").mkdir()
        response = await editor.get(BRANCHES, params={"path": str(root / name)})
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.json()["detail"].startswith("Not a git repository")

    async def test_a_checkout_on_master_only(self, editor: AsyncClient, root: Path) -> None:
        repo = init_repo(root / "legacy")
        run_git("branch", "-m", "main", "master", cwd=repo)
        response = await editor.get(BRANCHES, params={"path": str(repo)})
        assert response.json() == {
            "branches": ["master"],
            "detectedMain": "master",
            "detectedDevelop": None,
        }
