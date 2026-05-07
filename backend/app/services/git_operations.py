# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Git CLI wrappers, branch detection, and stash/restore helpers.

Provides async subprocess execution for git commands and an arbitrary
shell command runner.  ``run_git()`` delegates to ``_run_shell_cmd()``
internally so there is a single subprocess implementation.
"""

import asyncio
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)


async def _run_shell_cmd(
    args: list[str],
    cwd: str,
    timeout: int = 30,
    *,
    env: dict[str, str] | None = None,
) -> tuple[str, str, int]:
    """Run an arbitrary shell command asynchronously.

    Uses argv-form subprocess invocation (no shell) to avoid injection risks.

    Args:
        args: Command and arguments (e.g. ["gh", "pr", "view", ...]).
        cwd: Working directory for the command.
        timeout: Maximum seconds to wait.
        env: Optional environment override (e.g. ``GIT_SSH_COMMAND`` for
            SSH deploy keys). ``None`` means inherit the parent process
            env unchanged.

    Returns:
        Tuple of (stdout, stderr, returncode).
    """
    proc = await asyncio.create_subprocess_exec(
        *args,
        cwd=cwd,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    return (
        stdout.decode(errors="replace").strip(),
        stderr.decode(errors="replace").strip(),
        proc.returncode or 0,
    )


async def run_git(
    args: list[str],
    cwd: str,
    timeout: int = 60,
    *,
    env: dict[str, str] | None = None,
) -> tuple[str, str, int]:
    """Run a git command asynchronously.

    Delegates to ``_run_shell_cmd`` with ``git`` prepended.

    Args:
        args: Git subcommand and arguments.
        cwd: Working directory for the command.
        timeout: Maximum seconds to wait.
        env: Optional environment override forwarded to the subprocess —
            used by the scan-ingest auth refresh to pass
            ``GIT_SSH_COMMAND`` for SSH-cloned repos. ``None`` inherits.

    Returns:
        Tuple of (stdout, stderr, returncode).
    """
    return await _run_shell_cmd(["git", *args], cwd=cwd, timeout=timeout, env=env)


async def _detect_main_branch(repo_path: str) -> str | None:
    """Detect whether the repo uses 'main' or 'master' as its primary branch.

    Checks remote branches first, falls back to local branches for
    repos without a remote.

    Args:
        repo_path: Absolute path to the git repository.

    Returns:
        Branch name ('main' or 'master'), or None if neither found.
    """
    # Check remote branches first
    stdout, _, _ = await run_git(["branch", "-r"], cwd=repo_path)
    for candidate in ("origin/main", "origin/master"):
        if candidate in stdout:
            return candidate.split("/", 1)[1]
    # Fallback: check local branches (for repos without a remote)
    stdout, _, _ = await run_git(["branch"], cwd=repo_path)
    local_branches = {b.strip().lstrip("* ") for b in stdout.splitlines()}
    for candidate in ("main", "master"):
        if candidate in local_branches:
            return candidate
    return None


async def _detect_develop_branch(repo_path: str) -> str | None:
    """Detect whether the repo uses 'develop' or 'dev' as its development branch.

    Checks remote branches first, falls back to local branches for
    repos without a remote.

    Args:
        repo_path: Absolute path to the git repository.

    Returns:
        Branch name ('develop' or 'dev'), or None if neither found.
    """
    # Check remote branches first
    stdout, _, _ = await run_git(["branch", "-r"], cwd=repo_path)
    for candidate in ("origin/develop", "origin/dev"):
        if candidate in stdout:
            return candidate.split("/", 1)[1]
    # Fallback: check local branches
    stdout, _, _ = await run_git(["branch"], cwd=repo_path)
    local_branches = {b.strip().lstrip("* ") for b in stdout.splitlines()}
    for candidate in ("develop", "dev"):
        if candidate in local_branches:
            return candidate
    return None


async def detect_uncommitted_changes(repo_path: str) -> bool:
    """Run git status --porcelain. Returns True if working tree is dirty.

    Args:
        repo_path: Absolute path to the git repository.

    Returns:
        True if there are uncommitted changes.
    """
    stdout, _, _ = await run_git(["status", "--porcelain"], cwd=repo_path)
    return bool(stdout.strip())


async def stash_and_checkout_main(repo_path: str, main_branch: str) -> tuple[str, bool]:
    """Stash uncommitted changes and checkout the main branch for scanning.

    Records the current branch, stashes if dirty, and checks out the
    specified main branch so the scan always runs against canonical code.

    Args:
        repo_path: Absolute path to the git repository.
        main_branch: Name of the main branch (e.g. "main" or "master").

    Returns:
        Tuple of (original_branch, had_stash).

    Raises:
        RuntimeError: If checkout of main branch fails.
    """
    orig_branch, _, _ = await run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_path)
    orig_branch = orig_branch.strip()

    had_stash = False
    if await detect_uncommitted_changes(repo_path):
        await run_git(
            ["stash", "push", "-u", "-m", "bodhiorchard-scan-auto-stash"],
            cwd=repo_path,
        )
        had_stash = True
        logger.info("scan_stashed_changes", repo=repo_path)

    if orig_branch != main_branch:
        _, stderr, rc = await run_git(["checkout", main_branch], cwd=repo_path)
        if rc != 0 and "already used by worktree" in stderr:
            # Stale worktree locks the branch — remove it and retry
            worktree_dir = Path(repo_path) / ".bodhiorchard" / main_branch
            if worktree_dir.exists():
                await run_git(
                    ["worktree", "remove", str(worktree_dir), "--force"],
                    cwd=repo_path,
                )
                logger.info("scan_removed_stale_worktree", repo=repo_path, path=str(worktree_dir))
            _, stderr, rc = await run_git(["checkout", main_branch], cwd=repo_path)
        if rc != 0:
            if had_stash:
                await run_git(["stash", "pop"], cwd=repo_path)
            raise RuntimeError(f"Failed to checkout {main_branch}: {stderr[:200]}")
        logger.info(
            "scan_checked_out_main",
            repo=repo_path,
            from_branch=orig_branch,
            to_branch=main_branch,
        )

    # Pull latest (best-effort — diverged repos just use current HEAD)
    _, stderr, rc = await run_git(["pull", "--ff-only"], cwd=repo_path, timeout=120)
    if rc != 0:
        logger.warning(
            "scan_pull_ff_failed",
            repo=repo_path,
            stderr=stderr[:200],
        )

    return orig_branch, had_stash


async def restore_after_scan(repo_path: str, orig_branch: str, had_stash: bool) -> None:
    """Restore the original branch and stashed changes after scanning.

    Args:
        repo_path: Absolute path to the git repository.
        orig_branch: Branch name to switch back to.
        had_stash: Whether we stashed changes that need popping.
    """
    current, _, _ = await run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_path)
    if current.strip() != orig_branch and orig_branch != "HEAD":
        _, stderr, rc = await run_git(["checkout", orig_branch], cwd=repo_path)
        if rc != 0:
            logger.warning(
                "scan_restore_checkout_failed",
                repo=repo_path,
                branch=orig_branch,
                stderr=stderr[:200],
            )

    if had_stash:
        _, stderr, rc = await run_git(["stash", "pop"], cwd=repo_path)
        if rc != 0:
            logger.warning(
                "scan_restore_stash_pop_failed",
                repo=repo_path,
                stderr=stderr[:200],
            )
        else:
            logger.info("scan_restored_stash", repo=repo_path)


async def create_scan_worktree(repo_path: str, main_branch: str) -> str:
    """Create a temporary git worktree for scanning without touching the working tree.

    Creates a detached worktree at ``<repo>/.bodhiorchard/scan-wt`` pointing at
    the tip of ``main_branch``. This allows scanning the mainline code while
    the user continues working on their current branch.

    Args:
        repo_path: Absolute path to the git repository.
        main_branch: Branch to check out in the worktree (e.g. "main").

    Returns:
        Absolute path to the worktree directory.

    Raises:
        RuntimeError: If worktree creation fails.
    """
    wt_path = str(Path(repo_path) / ".bodhiorchard" / "scan-wt")

    # Clean up any stale worktree from a previous interrupted scan
    if Path(wt_path).exists():
        await run_git(["worktree", "remove", wt_path, "--force"], cwd=repo_path)

    _, stderr, rc = await run_git(
        ["worktree", "add", "--detach", wt_path, main_branch],
        cwd=repo_path,
    )
    if rc != 0:
        raise RuntimeError(f"Failed to create scan worktree: {stderr[:200]}")

    logger.info(
        "scan_worktree_created",
        repo=repo_path,
        worktree=wt_path,
        branch=main_branch,
    )
    return wt_path


async def remove_scan_worktree(repo_path: str) -> None:
    """Remove the temporary scan worktree.

    Safe to call even if the worktree doesn't exist.

    Args:
        repo_path: Absolute path to the git repository (not the worktree).
    """
    wt_path = str(Path(repo_path) / ".bodhiorchard" / "scan-wt")
    if not Path(wt_path).exists():
        return
    _, stderr, rc = await run_git(["worktree", "remove", wt_path, "--force"], cwd=repo_path)
    if rc != 0:
        logger.warning("scan_worktree_remove_failed", repo=repo_path, stderr=stderr[:200])
    else:
        logger.info("scan_worktree_removed", repo=repo_path)


async def get_github_repo_full_name(repo_path: str) -> str | None:
    """Extract owner/repo from the git origin remote URL.

    Supports both SSH (git@github.com:owner/repo.git) and
    HTTPS (https://github.com/owner/repo.git) formats.
    Returns None if not a GitHub remote.
    """
    import re

    try:
        stdout, _, _ = await run_git(["remote", "get-url", "origin"], cwd=repo_path)
    except Exception:
        return None

    url = stdout.strip()
    # SSH: git@github.com:owner/repo.git
    match = re.match(r"git@github\.com:(.+?)(?:\.git)?$", url)
    if match:
        return match.group(1)
    # HTTPS: https://github.com/owner/repo.git
    match = re.match(r"https://github\.com/(.+?)(?:\.git)?$", url)
    if match:
        return match.group(1)
    return None


async def list_remote_branches(repo_path: str) -> list[str]:
    """List all remote branch names (origin/main → 'main').

    Args:
        repo_path: Absolute path to the git repository.

    Returns:
        Sorted list of unique branch names.
    """
    stdout, _, _ = await run_git(["branch", "-r"], cwd=repo_path)
    branches = []
    for line in stdout.splitlines():
        line = line.strip()
        if "->" in line or not line:
            continue
        if "/" in line:
            branches.append(line.split("/", 1)[1])
    return sorted(set(branches))
