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
