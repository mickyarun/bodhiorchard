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

"""A hostile stored main branch can't send scan cleanup outside its worktree.

The scan worktree folder is named after the main branch. A ``..`` stored
before branch names were validated made that folder the shared
``scan-worktrees`` directory, and the dangling-worktree cleanup then
deleted every org's scan worktrees.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from app.config import settings as app_settings
from app.services.scan.stages import ingest_worktree as mod
from app.services.scan.stages._worktree_location import scan_worktree_parent


@pytest.fixture
def data_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setattr(app_settings.storage, "data_dir", str(tmp_path / "data"))
    return tmp_path / "data"


@pytest.fixture
def git_calls(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Stub git: the repo is on a feature branch and no folder is a worktree."""
    calls: list[list[str]] = []

    async def _fake_run_git(args: list[str], cwd: str, **_kw: Any) -> tuple[str, str, int]:
        calls.append(list(args))
        if args[:2] == ["rev-parse", "--abbrev-ref"]:
            return ("feature-x", "", 0)
        if args == ["rev-parse", "--git-common-dir"]:
            return ("", "fatal: not a git repository", 128)
        return ("", "", 0)

    monkeypatch.setattr(mod, "run_git", _fake_run_git)
    return calls


def _other_worktree(data_dir: Path) -> Path:
    keep = data_dir / "scan-worktrees" / "other-repo" / "main" / "src" / "app.py"
    keep.parent.mkdir(parents=True)
    keep.write_text("print('other org')\n")
    return keep


@pytest.mark.parametrize("branch", ["..", "."])
async def test_a_dot_branch_deletes_nothing_and_fails(
    data_dir: Path, git_calls: list[list[str]], branch: str
) -> None:
    keep = _other_worktree(data_dir)

    with pytest.raises(RuntimeError):
        await mod.ensure_scan_test_worktree("/srv/repos/acme/widgets", branch, skip_fetch=True)

    assert keep.is_file()
    assert not any(args[:2] == ["worktree", "add"] for args in git_calls)


async def test_a_valid_branch_still_rebuilds_its_own_worktree(
    data_dir: Path, git_calls: list[list[str]]
) -> None:
    keep = _other_worktree(data_dir)
    parent = scan_worktree_parent("/srv/repos/acme/widgets", org_id=None, repo_id=None)
    stale = parent / "release-uat"
    (stale / "old.txt").parent.mkdir(parents=True)
    (stale / "old.txt").write_text("stale\n")

    result = await mod.ensure_scan_test_worktree(
        "/srv/repos/acme/widgets", "release/uat", skip_fetch=True
    )

    assert result == str(stale)
    assert not (stale / "old.txt").exists()
    assert keep.is_file()
    assert ["worktree", "add", str(stale), "release/uat"] in git_calls
