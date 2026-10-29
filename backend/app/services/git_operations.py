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

"""Git CLI wrappers, branch detection, and stash/restore helpers.

Provides async subprocess execution for git commands and an arbitrary
shell command runner.  ``run_git()`` delegates to ``_run_shell_cmd()``
internally so there is a single subprocess implementation.
"""

import asyncio

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
    remote = set(await list_remote_branches(repo_path))
    for candidate in ("main", "master"):
        if candidate in remote:
            return candidate
    # Fallback: check local branches (for repos without a remote)
    local_branches = set(await list_local_branches(repo_path))
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
    remote = set(await list_remote_branches(repo_path))
    for candidate in ("develop", "dev"):
        if candidate in remote:
            return candidate
    # Fallback: check local branches
    local_branches = set(await list_local_branches(repo_path))
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


async def list_local_branches(repo_path: str) -> list[str]:
    """List local branch names, sorted.

    Reads refs directly rather than parsing ``git branch``: its output marks
    the current branch with ``*`` and a branch checked out in another
    worktree with ``+``. Onboarding checks ``develop`` out under
    ``.bodhiorchard/``, so parsing that text missed exactly the branch the
    develop detection looks for.

    Args:
        repo_path: Absolute path to the git repository.
    """
    stdout, _, _ = await run_git(
        ["for-each-ref", "--format=%(refname:short)", "refs/heads"], cwd=repo_path
    )
    return sorted({line.strip() for line in stdout.splitlines() if line.strip()})


async def list_remote_branches(repo_path: str) -> list[str]:
    """List the branch names on ``origin`` (``origin/main`` → ``main``).

    Reads ref names rather than ``git branch -r`` text, for the reason
    :func:`list_local_branches` gives, and so that callers compare whole
    names: searching that text took ``origin/devops`` for ``origin/dev``.
    ``lstrip=3`` drops ``refs/remotes/origin/`` and keeps slashes inside a
    branch name; the symbolic ``origin/HEAD`` is not a branch and is left out.

    Args:
        repo_path: Absolute path to the git repository.

    Returns:
        Sorted list of unique branch names.
    """
    stdout, _, _ = await run_git(
        ["for-each-ref", "--format=%(refname:lstrip=3)", "refs/remotes/origin"], cwd=repo_path
    )
    return sorted({line.strip() for line in stdout.splitlines() if line.strip()} - {"HEAD"})
