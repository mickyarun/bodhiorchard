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

"""Where the backend keeps its own git worktrees inside a tracked repo.

The scan pipeline checks ``develop`` and the setup branch out as linked
worktrees under ``<repo>/WORKTREES_DIR``. They only exist in the clone the
backend manages, so they are ignored through that clone's
``.git/info/exclude`` instead of the tracked ``.gitignore``: nothing about
them lands in a customer's commit history.

Clones set up before the Glideship rename keep these worktrees under
``<repo>/LEGACY_WORKTREES_DIR``. :func:`prepare_worktrees_dir` moves them
across the first time a scan touches the repo, using ``git worktree move``
so git's own registration follows the directory and nothing is left
registered at a path that no longer exists.
"""

from __future__ import annotations

from pathlib import Path

import structlog

from app.core.paths import rmtree_strictly_under
from app.services.git_operations import run_git
from app.services.repo_setup_names import LEGACY_WORKTREES_DIR, WORKTREES_DIR

logger = structlog.get_logger(__name__)

DEVELOP_WORKTREE = "develop"
SETUP_WORKTREE = "setup-work"

_EXCLUDE_ENTRY = f"/{WORKTREES_DIR}/"


def worktree_path(repo_path: str, name: str) -> Path:
    """Absolute path of the managed worktree ``name`` inside ``repo_path``."""
    return Path(repo_path) / WORKTREES_DIR / name


def existing_worktree(repo_path: str, name: str) -> Path | None:
    """The managed worktree ``name`` if it exists, in the new or legacy place.

    For readers outside the scan path, which can see a repo before its next
    scan has moved the worktrees across.
    """
    for root in (WORKTREES_DIR, LEGACY_WORKTREES_DIR):
        candidate = Path(repo_path) / root / name
        if candidate.exists():
            return candidate
    return None


async def prepare_worktrees_dir(repo_path: str) -> None:
    """Get ``repo_path`` ready for managed worktrees. Idempotent.

    Ignores ``WORKTREES_DIR`` in the clone's local exclude file, then moves
    any worktree still registered under the legacy folder into it.
    """
    await _exclude_worktrees_dir(repo_path)
    await _move_legacy_worktrees(repo_path)


async def _exclude_worktrees_dir(repo_path: str) -> None:
    """Add ``WORKTREES_DIR`` to the clone's ``info/exclude`` once."""
    out, stderr, rc = await run_git(["rev-parse", "--git-path", "info/exclude"], cwd=repo_path)
    if rc != 0:
        logger.warning("worktree_exclude_lookup_failed", repo=repo_path, error=stderr[:200])
        return
    exclude = Path(repo_path) / out.strip()
    # ``surrogateescape`` round-trips any non-UTF-8 bytes a developer's own
    # exclude file may hold, so appending never rewrites their entries.
    try:
        existing = (
            exclude.read_text(encoding="utf-8", errors="surrogateescape")
            if exclude.exists()
            else ""
        )
        if _EXCLUDE_ENTRY in existing.splitlines():
            return
        exclude.parent.mkdir(parents=True, exist_ok=True)
        separator = "" if not existing or existing.endswith("\n") else "\n"
        exclude.write_text(
            f"{existing}{separator}{_EXCLUDE_ENTRY}\n",
            encoding="utf-8",
            errors="surrogateescape",
        )
    except OSError as exc:
        logger.warning("worktree_exclude_write_failed", repo=repo_path, error=str(exc)[:200])


async def _move_legacy_worktrees(repo_path: str) -> None:
    """Move every worktree registered under the legacy folder into the new one.

    Each keeps its path relative to the root, so ``.bodhiorchard/develop``
    becomes ``.glideship/worktrees/develop``. The legacy folder itself stays:
    older setups track their MCP bridge in it.
    """
    legacy_root = (Path(repo_path) / LEGACY_WORKTREES_DIR).resolve()
    if not legacy_root.is_dir():
        return
    registered = await _registered_worktree_paths(repo_path)
    for old in registered:
        if not old.is_relative_to(legacy_root) or not old.exists():
            continue
        new = (Path(repo_path) / WORKTREES_DIR / old.relative_to(legacy_root)).resolve()
        await _move_worktree(repo_path, old, new, registered)


async def _registered_worktree_paths(repo_path: str) -> list[Path]:
    """Resolved paths of every worktree ``git worktree list`` knows about."""
    out, stderr, rc = await run_git(["worktree", "list", "--porcelain"], cwd=repo_path)
    if rc != 0:
        logger.warning("worktree_list_failed", repo=repo_path, error=stderr[:200])
        return []
    prefix = "worktree "
    return [
        Path(line[len(prefix) :]).resolve() for line in out.splitlines() if line.startswith(prefix)
    ]


async def _move_worktree(repo_path: str, old: Path, new: Path, registered: list[Path]) -> None:
    """Move one legacy worktree to ``new``, or drop it if ``new`` is taken.

    A worktree already registered at ``new`` is the live one, so the legacy
    copy is removed. An unregistered directory at ``new`` is debris from a
    crashed run and is cleared so the move can land.
    """
    if new in registered:
        await _remove_worktree(repo_path, old)
        return
    if new.exists():
        rmtree_strictly_under(new, Path(repo_path) / WORKTREES_DIR)
    new.parent.mkdir(parents=True, exist_ok=True)
    _, stderr, rc = await run_git(["worktree", "move", str(old), str(new)], cwd=repo_path)
    if rc != 0:
        # ``move`` refuses worktrees with submodules. Every managed worktree
        # is recreated on demand, so removing it is the safe fallback.
        logger.warning("legacy_worktree_move_failed", repo=repo_path, error=stderr[:200])
        await _remove_worktree(repo_path, old)
        return
    logger.info("legacy_worktree_moved", repo=repo_path, old=str(old), new=str(new))


async def _remove_worktree(repo_path: str, path: Path) -> None:
    """Force-remove one legacy worktree, logging when git refuses."""
    _, stderr, rc = await run_git(["worktree", "remove", "--force", str(path)], cwd=repo_path)
    if rc != 0:
        logger.warning("legacy_worktree_remove_failed", repo=repo_path, error=stderr[:200])
        return
    logger.info("legacy_worktree_removed", repo=repo_path, path=str(path))
