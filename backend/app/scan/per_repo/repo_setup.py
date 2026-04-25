# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Phase B1 — bootstrap a tracked repo's Bodhiorchard configuration.

Per-repo setup that runs once on the first scan (and is idempotent on
subsequent scans):

1. Worktrees on ``main`` and ``develop`` so the orchestrator can do
   branch-aware work without disturbing the user's working tree.
2. ``main_branch`` / ``develop_branch`` detection if the row was added
   without explicit values (legacy ``Add Repo`` UX).
3. MCP server config (``.mcp.json``) so Claude Code launched inside
   the repo can talk back to Bodhiorchard.
4. Git hooks (``.githooks/`` + ``core.hooksPath``) and Claude Code
   hooks (``.claude/hooks/`` + ``settings.json``).
5. ``.gitignore`` carve-out for ``.bodhiorchard/``, package-script
   prep, and the workflow paragraph appended to ``CLAUDE.md``.
6. If any file actually changed, branch + commit + push + PR.

Failures are caught and logged but never propagated — Bodhiorchard
must keep scanning even when one repo's worktree push hits a stale
remote token. Returns a UI-facing string when a setup branch was
pushed but no PR could be opened.
"""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)


async def phase_b1_repo_setup(
    db: AsyncSession,
    org_id: uuid.UUID,
    repo_path: str,
    repo_name: str,
    tracked_repo: object | None,
    scan_id: str,
    base_pct: int,
) -> str | None:
    """Phase B1: Worktrees, MCP init, hooks, .gitignore, commit+push+PR.

    Reports granular progress for each sub-step.

    Args:
        db: Async database session.
        org_id: Organization UUID.
        repo_path: Absolute path to the repository.
        repo_name: Name of the repository.
        tracked_repo: TrackedRepository model instance (or None).
        scan_id: Scan identifier for logging and progress tracking.
        base_pct: Base progress percentage for this repo's range.

    Returns:
        Setup PR message string if a PR was created without a URL, else None.
    """
    from app.config import settings as app_settings
    from app.services.git_operations import _detect_develop_branch, _detect_main_branch
    from app.services.repo_setup import (
        add_bodhiorchard_gitignore,
        add_prepare_script,
        append_bodhiorchard_claude_instructions,
        commit_and_push_bodhiorchard_setup,
        create_setup_pr,
        ensure_repo_worktrees,
        init_bodhiorchard_mcp_in_repo,
        install_claude_hooks,
        install_hooks,
    )
    from app.services.scan_progress import update_scan_progress

    setup_pr_message: str | None = None

    try:
        await update_scan_progress(
            scan_id,
            status="setting_up_worktrees",
            progress_pct=base_pct + 18,
        )
        main_wt, develop_wt = await ensure_repo_worktrees(repo_path)
        del main_wt, develop_wt  # paths consumed by the worktree-aware tools below

        # Persist detected branches to tracked_repositories
        if tracked_repo:
            if tracked_repo.main_branch is None:  # type: ignore[union-attr]
                detected_main = await _detect_main_branch(repo_path)
                if detected_main:
                    tracked_repo.main_branch = detected_main  # type: ignore[union-attr]
            if tracked_repo.develop_branch is None:  # type: ignore[union-attr]
                detected_dev = await _detect_develop_branch(repo_path)
                if detected_dev:
                    tracked_repo.develop_branch = detected_dev  # type: ignore[union-attr]

        # Init Bodhiorchard MCP in repo (skips if already configured)
        await update_scan_progress(
            scan_id,
            status="setting_up_mcp",
            progress_pct=base_pct + 22,
        )
        mcp_changed = await init_bodhiorchard_mcp_in_repo(
            repo_path,
            app_settings.public_url,
        )

        # Install git hooks to .githooks/ + set core.hooksPath
        await update_scan_progress(
            scan_id,
            status="installing_hooks",
            progress_pct=base_pct + 25,
        )
        hooks_changed = await install_hooks(repo_path, app_settings.public_url, str(org_id))

        # Install Claude Code hooks (.claude/hooks/ + settings.json)
        claude_hooks_changed = await install_claude_hooks(
            repo_path,
            app_settings.public_url,
        )

        # Ensure hooks are active regardless of commit/push status
        from app.services.git_operations import run_git

        await run_git(["config", "core.hooksPath", ".githooks"], cwd=repo_path)

        # Add .bodhiorchard/ to .gitignore
        gitignore_changed = add_bodhiorchard_gitignore(repo_path)

        # Add prepare script to package.json
        prepare_changed = add_prepare_script(repo_path)

        # Add Bodhiorchard workflow instructions to CLAUDE.md
        claude_md_changed = append_bodhiorchard_claude_instructions(repo_path)

        # Branch, commit, push setup files, and create PR
        any_changed = (
            mcp_changed
            or hooks_changed
            or claude_hooks_changed
            or gitignore_changed
            or prepare_changed
            or claude_md_changed
        )
        if any_changed:
            await update_scan_progress(
                scan_id,
                status="pushing_setup",
                progress_pct=base_pct + 28,
            )
            base = (
                tracked_repo.main_branch  # type: ignore[union-attr]
                if tracked_repo and tracked_repo.main_branch  # type: ignore[union-attr]
                else "main"
            )
            pushed_branch = await commit_and_push_bodhiorchard_setup(repo_path, base)
            if pushed_branch:
                logger.info(
                    "bodhiorchard_setup_branch_pushed",
                    repo=repo_name,
                    branch=pushed_branch,
                )
                pr_url = await create_setup_pr(repo_path, base, pushed_branch)
                if pr_url:
                    logger.info(
                        "bodhiorchard_setup_pr_created",
                        repo=repo_name,
                        url=pr_url,
                    )
                else:
                    setup_pr_message = (
                        f"Setup branch '{pushed_branch}' pushed "
                        f"to {repo_name}. Create a PR manually "
                        "to merge the Bodhiorchard config files."
                    )

            await db.flush()
    except Exception:
        logger.exception(
            "scan_repo_setup_failed",
            scan_id=scan_id,
            repo=repo_name,
        )

    return setup_pr_message
