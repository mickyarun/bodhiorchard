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

"""Every ``rmtree`` in the cloner stays inside the clone root.

Segment checks keep ``..`` out of clone paths, but an org folder that is
a symlink to somewhere else still resolves outside the clone root. The
cloner resolves the target before deleting and refuses anything that
isn't strictly inside its parent folder and the clone root.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from app.config import settings as app_settings
from app.services import repo_cloner


@pytest.fixture
def repos_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setattr(app_settings.storage, "data_dir", str(tmp_path / "data"))
    root = app_settings.storage.repos_dir
    root.mkdir(parents=True)
    return root


@pytest.fixture
def outside(tmp_path: Path) -> Path:
    """A folder outside the clone root holding a repo-shaped tree."""
    victim = tmp_path / "elsewhere"
    (victim / "widgets" / ".git").mkdir(parents=True)
    return victim


@pytest.fixture
def linked_org(repos_dir: Path, outside: Path) -> str:
    """An org folder under the clone root that is a symlink to ``outside``."""
    (repos_dir / "acme").symlink_to(outside, target_is_directory=True)
    return "acme"


def test_purge_repo_refuses_a_target_that_resolves_outside(outside: Path, linked_org: str) -> None:
    assert repo_cloner.purge_repo_clones(linked_org, ["widgets"]) == 0
    assert (outside / "widgets" / ".git").is_dir()


def test_purge_org_refuses_an_org_folder_that_resolves_outside(
    outside: Path, linked_org: str
) -> None:
    assert repo_cloner.purge_org_clones(linked_org) == 0
    assert (outside / "widgets" / ".git").is_dir()


async def test_failed_clone_cleanup_refuses_a_target_outside(
    monkeypatch: pytest.MonkeyPatch, outside: Path, linked_org: str
) -> None:
    (outside / "widgets" / ".git").rmdir()

    async def _clone_fails(args: list[str], **_: Any) -> tuple[int, str, str]:
        # git writes ``.git`` into the destination before failing.
        Path(args[-1], ".git").mkdir(parents=True)
        return 128, "", "fatal: remote hung up"

    monkeypatch.setattr(repo_cloner, "_run_git", _clone_fails)
    result = await repo_cloner.clone_or_update(
        "https://github.com/acme/widgets", org_slug=linked_org
    )
    assert result.success is False
    assert (outside / "widgets" / ".git").is_dir()


def test_purges_still_delete_inside_the_root(repos_dir: Path) -> None:
    for repo in ("widgets", "gadgets"):
        (repos_dir / "acme" / repo / ".git").mkdir(parents=True)
    assert repo_cloner.purge_repo_clones("acme", ["widgets"]) == 1
    assert not (repos_dir / "acme" / "widgets").exists()
    assert repo_cloner.purge_org_clones("acme") == 1
    assert not (repos_dir / "acme").exists()
    assert repos_dir.is_dir()


async def test_failed_clone_cleanup_still_removes_its_own_dest(
    monkeypatch: pytest.MonkeyPatch, repos_dir: Path
) -> None:
    async def _clone_fails(args: list[str], **_: Any) -> tuple[int, str, str]:
        Path(args[-1], ".git").mkdir(parents=True)
        return 128, "", "fatal: remote hung up"

    monkeypatch.setattr(repo_cloner, "_run_git", _clone_fails)
    result = await repo_cloner.clone_or_update("https://github.com/acme/widgets", org_slug="acme")
    assert result.success is False
    assert not (repos_dir / "acme" / "widgets").exists()
    assert (repos_dir / "acme").is_dir()
