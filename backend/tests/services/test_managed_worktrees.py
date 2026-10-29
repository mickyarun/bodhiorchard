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
"""Managed worktrees move from ``.bodhiorchard/`` to ``.glideship/worktrees/``.

Every test runs against a real git repo laid out the way a clone set up
before the rename looks, then drives the scan's own entry points
(``ensure_repo_worktrees`` / ``prepare_setup_worktree``) over it.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from app.services.managed_worktrees import (
    DEVELOP_WORKTREE,
    SETUP_WORKTREE,
    existing_worktree,
    worktree_path,
)
from app.services.repo_setup import ensure_repo_worktrees, prepare_setup_worktree

_LEGACY = ".bodhiorchard"
_SETUP_BRANCH = "bodhiorchard/init-setup"


def _git(*args: str, cwd: Path) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def _registered(repo: Path) -> list[Path]:
    out = _git("worktree", "list", "--porcelain", cwd=repo)
    return [
        Path(line[len("worktree ") :]) for line in out.splitlines() if line.startswith("worktree ")
    ]


def _legacy_repo(tmp_path: Path) -> Path:
    """A clone with develop + setup-work worktrees under ``.bodhiorchard/``.

    It also tracks a bridge under the legacy folder and ignores the folder
    in ``.gitignore``, as the old setup PR did.
    """
    repo = tmp_path / "taskflow"
    repo.mkdir()
    _git("init", "-q", "-b", "main", cwd=repo)
    (repo / _LEGACY).mkdir()
    (repo / _LEGACY / "mcp_bridge.py").write_text("# bridge\n")
    (repo / ".gitignore").write_text(f"{_LEGACY}/\n")
    _git("add", "-f", ".gitignore", f"{_LEGACY}/mcp_bridge.py", cwd=repo)
    _git("commit", "-q", "-m", "init", cwd=repo)
    _git("branch", "develop", cwd=repo)
    _git("worktree", "add", "-q", str(repo / _LEGACY / "develop"), "develop", cwd=repo)
    _git(
        "worktree",
        "add",
        "-q",
        "-B",
        _SETUP_BRANCH,
        str(repo / _LEGACY / "setup-work"),
        "main",
        cwd=repo,
    )
    return repo


def _assert_new_layout(repo: Path) -> None:
    develop = worktree_path(str(repo), DEVELOP_WORKTREE).resolve()
    registered = [p.resolve() for p in _registered(repo)]
    assert develop in registered
    assert not any(p.is_relative_to((repo / _LEGACY).resolve()) for p in registered)
    assert not (repo / _LEGACY / "develop").exists()
    # The tracked bridge in the legacy folder is left alone.
    assert (repo / _LEGACY / "mcp_bridge.py").exists()
    # The new folder is ignored locally, so the checkout stays clean.
    assert _git("status", "--porcelain", cwd=repo) == ""


async def test_ensure_moves_legacy_worktrees(tmp_path: Path) -> None:
    repo = _legacy_repo(tmp_path)
    marker = repo / _LEGACY / "develop" / "local-only.txt"
    marker.write_text("kept\n")

    _, develop = await ensure_repo_worktrees(str(repo))

    assert develop == str(worktree_path(str(repo), DEVELOP_WORKTREE))
    _assert_new_layout(repo)
    # Moved, not recreated: untracked files in the worktree survive.
    assert (Path(develop) / "local-only.txt").read_text() == "kept\n"
    assert worktree_path(str(repo), SETUP_WORKTREE).exists()


async def test_rerun_is_idempotent(tmp_path: Path) -> None:
    repo = _legacy_repo(tmp_path)

    first = await ensure_repo_worktrees(str(repo))
    second = await ensure_repo_worktrees(str(repo))

    assert first == second
    _assert_new_layout(repo)
    exclude = Path(_git("rev-parse", "--git-path", "info/exclude", cwd=repo).strip())
    entries = (repo / exclude).read_text().splitlines()
    assert entries.count("/.glideship/worktrees/") == 1


async def test_setup_worktree_reclaims_setup_branch(tmp_path: Path) -> None:
    """The legacy setup-work holds the setup branch; setup must still start."""
    repo = _legacy_repo(tmp_path)

    work = await prepare_setup_worktree(str(repo), "main")

    assert work == str(worktree_path(str(repo), SETUP_WORKTREE))
    branch = _git("rev-parse", "--abbrev-ref", "HEAD", cwd=Path(work)).strip()
    assert branch == _SETUP_BRANCH
    _assert_new_layout(repo)


async def test_debris_at_new_path_does_not_block_move(tmp_path: Path) -> None:
    repo = _legacy_repo(tmp_path)
    debris = worktree_path(str(repo), DEVELOP_WORKTREE)
    debris.mkdir(parents=True)
    (debris / "stale.txt").write_text("x\n")

    await ensure_repo_worktrees(str(repo))

    _assert_new_layout(repo)
    assert not (debris / "stale.txt").exists()


async def test_legacy_copy_dropped_when_new_path_is_live(tmp_path: Path) -> None:
    """A worktree already registered at the new path wins over the legacy one."""
    repo = _legacy_repo(tmp_path)
    live = worktree_path(str(repo), "scan-wt")
    _git("worktree", "add", "-q", "--detach", str(live), "main", cwd=repo)
    _git("worktree", "add", "-q", "--detach", str(repo / _LEGACY / "scan-wt"), "main", cwd=repo)

    await ensure_repo_worktrees(str(repo))

    _assert_new_layout(repo)
    assert live.resolve() in [p.resolve() for p in _registered(repo)]


async def test_fresh_repo_gets_new_layout_only(tmp_path: Path) -> None:
    repo = tmp_path / "fresh"
    repo.mkdir()
    _git("init", "-q", "-b", "main", cwd=repo)
    _git("commit", "-q", "--allow-empty", "-m", "init", cwd=repo)
    _git("branch", "develop", cwd=repo)

    _, develop = await ensure_repo_worktrees(str(repo))

    assert develop == str(worktree_path(str(repo), DEVELOP_WORKTREE))
    assert not (repo / _LEGACY).exists()
    assert _git("status", "--porcelain", cwd=repo) == ""


def test_existing_worktree_falls_back_to_legacy(tmp_path: Path) -> None:
    (tmp_path / _LEGACY / DEVELOP_WORKTREE).mkdir(parents=True)

    assert existing_worktree(str(tmp_path), DEVELOP_WORKTREE) == (
        tmp_path / _LEGACY / DEVELOP_WORKTREE
    )
    worktree_path(str(tmp_path), DEVELOP_WORKTREE).mkdir(parents=True)
    assert existing_worktree(str(tmp_path), DEVELOP_WORKTREE) == worktree_path(
        str(tmp_path), DEVELOP_WORKTREE
    )
    assert existing_worktree(str(tmp_path), "missing") is None


async def test_non_utf8_exclude_is_kept_byte_for_byte(tmp_path: Path) -> None:
    """A developer's own exclude file may hold any bytes; append, never rewrite."""
    repo = tmp_path / "hybrid"
    repo.mkdir()
    _git("init", "-q", "-b", "main", cwd=repo)
    _git("commit", "-q", "--allow-empty", "-m", "init", cwd=repo)
    exclude = repo / _git("rev-parse", "--git-path", "info/exclude", cwd=repo).strip()
    exclude.write_bytes(b"caf\xe9.log\n")

    await ensure_repo_worktrees(str(repo))

    assert exclude.read_bytes() == b"caf\xe9.log\n/.glideship/worktrees/\n"
