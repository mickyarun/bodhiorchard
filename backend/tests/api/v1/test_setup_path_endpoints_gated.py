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

"""The two path-taking setup endpoints have two independent guards.

``browse_directories`` and ``get_repo_branches`` are unauthenticated — the
wizard needs a directory picker before an org or a JWT exists — and both take
a caller-chosen filesystem path. They are confined twice over:

* **in time**, by ``_require_setup_incomplete``: once an organization row
  exists they 403, like every other pre-auth endpoint in that router. Left
  open they were a filesystem walker and a filesystem prober for anyone who
  could reach the port.
* **in space**, by ``picker_roots``: the resolved path must stay under the
  home directory, so the window while setup *is* open is a picker over a
  home directory rather than over the host.

Guards with no tests are guards that get deleted, so each is asserted in
both directions — refusing what it should, and still allowing the case it
exists to permit.

Same harness style as ``test_setup_two_stage.py``: the handlers are called
directly with the organization lookup stubbed, since the repo has no
HTTP+DB fixture (see ``tests/conftest.py``).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi import HTTPException, status

from app.api.v1 import setup as setup_api


class _OrgRepoStub:
    """Stands in for ``OrganizationRepository``; only the guard's call."""

    setup_exists: Any = None

    def __init__(self, _db: Any) -> None:
        pass

    async def check_setup_exists(self) -> Any:
        return type(self).setup_exists


@pytest.fixture
def setup_complete(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the guard see an existing organization."""
    _OrgRepoStub.setup_exists = object()
    monkeypatch.setattr(setup_api, "OrganizationRepository", _OrgRepoStub)


@pytest.fixture
def setup_open(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the guard see a fresh install with no organization yet."""
    _OrgRepoStub.setup_exists = None
    monkeypatch.setattr(setup_api, "OrganizationRepository", _OrgRepoStub)


@pytest.fixture
def picker_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Point the allowed root at a temp directory, not the real home.

    ``tmp_path`` sits outside ``$HOME``, so without this every call in this
    module would be refused for the wrong reason — and the alternative,
    writing fixtures into the developer's actual home directory, is worse.
    """
    monkeypatch.setattr(setup_api, "picker_roots", lambda: (tmp_path,))
    return tmp_path


class TestClosesWhenSetupCompletes:
    """The time guard: both endpoints shut once an org exists."""

    async def test_browse_directories(self, setup_complete: None, picker_root: Path) -> None:
        with pytest.raises(HTTPException) as caught:
            await setup_api.browse_directories(path=str(picker_root), db=None)  # type: ignore[arg-type]
        assert caught.value.status_code == status.HTTP_403_FORBIDDEN

    async def test_repo_branches(self, setup_complete: None, picker_root: Path) -> None:
        with pytest.raises(HTTPException) as caught:
            await setup_api.get_repo_branches(path=str(picker_root), db=None)  # type: ignore[arg-type]
        assert caught.value.status_code == status.HTTP_403_FORBIDDEN


class TestConfinedToTheRoots:
    """The space guard: nothing outside the allowed roots, by any route."""

    async def test_browse_refuses_a_path_outside(
        self, setup_open: None, picker_root: Path
    ) -> None:
        with pytest.raises(HTTPException) as caught:
            await setup_api.browse_directories(path="/etc", db=None)  # type: ignore[arg-type]
        assert caught.value.status_code == status.HTTP_403_FORBIDDEN

    async def test_browse_refuses_traversal_out_of_a_root(
        self, setup_open: None, picker_root: Path
    ) -> None:
        """``..`` is collapsed before the check, so it cannot climb out."""
        with pytest.raises(HTTPException) as caught:
            await setup_api.browse_directories(path=f"{picker_root}/../../..", db=None)  # type: ignore[arg-type]
        assert caught.value.status_code == status.HTTP_403_FORBIDDEN

    async def test_browse_refuses_a_symlink_escape(
        self, setup_open: None, picker_root: Path
    ) -> None:
        """realpath follows the link, so a link out of the root is caught."""
        escape = picker_root / "escape"
        escape.symlink_to("/etc")
        with pytest.raises(HTTPException) as caught:
            await setup_api.browse_directories(path=str(escape), db=None)  # type: ignore[arg-type]
        assert caught.value.status_code == status.HTTP_403_FORBIDDEN

    async def test_repo_branches_refuses_a_path_outside(
        self, setup_open: None, picker_root: Path
    ) -> None:
        with pytest.raises(HTTPException) as caught:
            await setup_api.get_repo_branches(path="/etc", db=None)  # type: ignore[arg-type]
        assert caught.value.status_code == status.HTTP_403_FORBIDDEN


class TestStillServesTheWizard:
    """Neither guard may break the case they exist to allow."""

    async def test_browse_lists_directories_under_a_root(
        self, setup_open: None, picker_root: Path
    ) -> None:
        (picker_root / "repos").mkdir()
        (picker_root / "notes.txt").write_text("not a directory")

        result = await setup_api.browse_directories(path=str(picker_root), db=None)  # type: ignore[arg-type]

        assert result.current_path == str(picker_root)
        assert [entry.name for entry in result.directories] == ["repos"]

    async def test_browse_walks_into_a_subdirectory(
        self, setup_open: None, picker_root: Path
    ) -> None:
        nested = picker_root / "repos" / "project"
        nested.mkdir(parents=True)

        result = await setup_api.browse_directories(path=str(nested.parent), db=None)  # type: ignore[arg-type]

        assert [entry.name for entry in result.directories] == ["project"]

    def test_the_default_root_is_the_home_directory(self) -> None:
        """The shipped root, which the fixture above deliberately replaces."""
        assert setup_api.picker_roots() == (Path.home(),)
