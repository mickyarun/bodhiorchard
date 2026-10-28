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
"""Branch detection on local checkouts, including onboarded ones.

Onboarding checks ``develop`` out in a worktree under ``.bodhiorchard/``,
and ``git branch`` then prints it as ``+ develop``. Detection must read the
branch names themselves, not that decorated text.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from app.services.git_operations import (
    _detect_develop_branch,
    _detect_main_branch,
    list_local_branches,
    list_remote_branches,
)


def _git(*args: str, cwd: Path) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
    )


def _repo_with_develop(tmp_path: Path) -> Path:
    repo = tmp_path / "taskflow"
    repo.mkdir()
    _git("init", "-q", "-b", "main", cwd=repo)
    _git("commit", "-q", "--allow-empty", "-m", "init", cwd=repo)
    _git("branch", "develop", cwd=repo)
    return repo


async def test_finds_develop_checked_out_in_another_worktree(tmp_path: Path) -> None:
    repo = _repo_with_develop(tmp_path)
    _git("worktree", "add", "-q", str(repo / ".bodhiorchard" / "develop"), "develop", cwd=repo)

    assert await _detect_main_branch(str(repo)) == "main"
    assert await _detect_develop_branch(str(repo)) == "develop"


async def test_lists_local_branches_without_markers(tmp_path: Path) -> None:
    repo = _repo_with_develop(tmp_path)
    _git("worktree", "add", "-q", str(tmp_path / "wt"), "develop", cwd=repo)

    assert await list_local_branches(str(repo)) == ["develop", "main"]


def _clone_with_remote_branches(tmp_path: Path, default: str, *branches: str) -> Path:
    """A clone whose origin has ``branches``; only ``default`` exists locally.

    ``set-head --auto`` adds the symbolic ``origin/HEAD``, which ``git branch
    -r`` prints as ``origin/HEAD -> origin/<default>``.
    """
    origin = tmp_path / "origin.git"
    _git("init", "-q", "--bare", "-b", default, str(origin), cwd=tmp_path)
    repo = tmp_path / "clone"
    _git("clone", "-q", str(origin), str(repo), cwd=tmp_path)
    _git("commit", "-q", "--allow-empty", "-m", "init", cwd=repo)
    _git("push", "-q", "origin", *(f"HEAD:{b}" for b in branches), cwd=repo)
    _git("fetch", "-q", "origin", cwd=repo)
    _git("remote", "set-head", "origin", "--auto", cwd=repo)
    return repo


async def test_remote_branches_are_matched_whole_not_by_prefix(tmp_path: Path) -> None:
    """``origin/devops`` is not ``dev`` and ``origin/main-legacy`` is not ``main``."""
    repo = _clone_with_remote_branches(tmp_path, "master", "master", "main-legacy", "devops")
    # Only master is local, so the local fallback cannot hide a wrong remote match.
    assert await list_local_branches(str(repo)) == ["master"]

    assert await _detect_main_branch(str(repo)) == "master"
    assert await _detect_develop_branch(str(repo)) is None


async def test_exact_remote_names_are_still_found(tmp_path: Path) -> None:
    repo = _clone_with_remote_branches(tmp_path, "main", "main", "dev", "develop-old", "feature/x")

    assert await _detect_main_branch(str(repo)) == "main"
    assert await _detect_develop_branch(str(repo)) == "dev"


async def test_remote_listing_keeps_slashes_and_drops_head(tmp_path: Path) -> None:
    """One helper feeds detection and the branch pickers; ``HEAD`` is not a branch."""
    repo = _clone_with_remote_branches(tmp_path, "main", "main", "feature/x")
    _git("remote", "add", "upstream", str(tmp_path / "origin.git"), cwd=repo)
    _git("fetch", "-q", "upstream", cwd=repo)
    _git("config", "color.branch", "always", cwd=repo)
    _git("config", "column.branch", "always", cwd=repo)

    assert await list_remote_branches(str(repo)) == ["feature/x", "main"]
