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

"""Worktree helpers for the ``ingest`` stage.

Mirrors ``app/services/repo_setup.py::ensure_repo_worktrees`` semantics
so ingest behaves the same way the live scan does, just under a
distinct parent dir (``<repo>/.bodhiorchard/scan-test``) so the two
pipelines don't share state.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING

import structlog

from app.services.git_operations import run_git
from app.services.scan.stages._origin_auth import refresh_origin_auth

if TYPE_CHECKING:
    from app.models.organization import Organization

logger = structlog.get_logger(__name__)

# Sandbox worktree parent — kept under ``<repo>/.bodhiorchard/`` for
# parity with the production scan but under a distinct subdir so the
# two never collide.
WORKTREE_PARENT = ".bodhiorchard/scan-test"


async def _has_origin_remote(repo_path: str) -> bool:
    """Return True iff the repo has an ``origin`` remote configured."""
    _, _, rc = await run_git(["remote", "get-url", "origin"], cwd=repo_path)
    return rc == 0


async def ensure_scan_test_worktree(
    repo_path: str,
    main_branch: str,
    *,
    skip_fetch: bool,
    org: Organization | None = None,
) -> str:
    """Create or refresh the sandbox worktree.

    Resolution order:

    * If the repo is already on ``main_branch`` at its root, use
      ``repo_path`` directly. Git refuses to ``worktree add`` a branch
      that's already checked out elsewhere, so materialising a separate
      worktree would fail.
    * Otherwise, materialise (or adopt) ``<repo>/.bodhiorchard/scan-test/<branch>``,
      then fetch + hard-reset it to ``origin/<main_branch>`` (or the local
      branch ref if there's no ``origin`` remote — e.g. local-path imports).
    * If a stale registration points to a missing dir, prune and recreate.

    Returns the absolute path of the worktree to operate on.
    """
    current_branch_out, _, _ = await run_git(
        ["rev-parse", "--abbrev-ref", "HEAD"],
        cwd=repo_path,
    )
    current_branch = current_branch_out.strip()
    has_origin = await _has_origin_remote(repo_path)

    if current_branch == main_branch:
        if not skip_fetch:
            await fetch_and_reset(repo_path, main_branch, has_origin=has_origin, org=org)
        return repo_path

    repo = Path(repo_path)
    parent = repo / WORKTREE_PARENT
    parent.mkdir(parents=True, exist_ok=True)
    wt_path = parent / main_branch.replace("/", "-")
    wt_str = str(wt_path)

    await run_git(["worktree", "prune"], cwd=repo_path)

    if not wt_path.exists():
        _, stderr, rc = await run_git(
            ["worktree", "add", wt_str, main_branch],
            cwd=repo_path,
        )
        if rc != 0:
            # Branch may not have a local ref yet — try creating from origin
            # (only meaningful when ``origin`` exists).
            if not has_origin:
                raise RuntimeError(f"git worktree add failed (no origin): {stderr[:200]}")
            _, stderr2, rc2 = await run_git(
                ["worktree", "add", "-B", main_branch, wt_str, f"origin/{main_branch}"],
                cwd=repo_path,
            )
            if rc2 != 0:
                raise RuntimeError(f"git worktree add failed: {stderr[:200]} / {stderr2[:200]}")

    if skip_fetch:
        return wt_str

    await fetch_and_reset(
        repo_path,
        main_branch,
        worktree=wt_str,
        has_origin=has_origin,
        org=org,
    )
    return wt_str


async def fetch_and_reset(
    repo_path: str,
    main_branch: str,
    *,
    worktree: str | None = None,
    has_origin: bool | None = None,
    org: Organization | None = None,
) -> None:
    """Fetch origin (if present) and hard-reset the target tree.

    With an ``origin`` remote, refreshes the origin auth (fresh GitHub
    App installation token, or ``GIT_SSH_COMMAND`` for SSH deploy keys —
    see :mod:`._origin_auth`), fetches, and resets to
    ``origin/<main_branch>``. Without an origin (e.g. local-path imports),
    skips the fetch and resets to the local ``<main_branch>`` ref instead.

    ``worktree`` is the path to reset; defaults to ``repo_path`` itself.
    ``org`` carries the GitHub App credentials when present; pass ``None``
    for sandbox / test runs without org context.
    """
    target = worktree or repo_path
    if has_origin is None:
        has_origin = await _has_origin_remote(repo_path)

    if has_origin:
        env = await refresh_origin_auth(repo_path, org)
        _, stderr, rc = await run_git(
            ["fetch", "origin", "--prune"],
            cwd=repo_path,
            env=env,
        )
        if rc != 0:
            logger.warning("scan_ingest_fetch_failed", error=stderr[:200])
        reset_ref = f"origin/{main_branch}"
    else:
        reset_ref = main_branch

    _, stderr, rc = await run_git(["reset", "--hard", reset_ref], cwd=target)
    if rc == 0:
        return

    if worktree is None:
        # Reset failed on the live repo path — propagate so the
        # operator sees uncommitted-changes errors etc., rather than
        # silently continuing with a stale tree.
        raise RuntimeError(f"failed to reset {repo_path} to {reset_ref}: {stderr[:200]}")

    # For worktrees we rebuild on failure (matches prior behaviour).
    wt_path = Path(worktree)
    shutil.rmtree(wt_path, ignore_errors=True)
    await run_git(["worktree", "prune"], cwd=repo_path)
    _, stderr2, rc2 = await run_git(
        ["worktree", "add", "-B", main_branch, worktree, reset_ref],
        cwd=repo_path,
    )
    if rc2 != 0:
        raise RuntimeError(f"failed to refresh worktree: {stderr[:200]} / {stderr2[:200]}")
