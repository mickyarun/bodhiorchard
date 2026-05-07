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

from app.config import settings as app_settings
from app.models.organization import Organization
from app.models.tracked_repository import TrackedRepository
from app.services.git_operations import (
    _detect_develop_branch,
    _detect_main_branch,
    get_github_repo_full_name,
    run_git,
)
from app.services.repo_setup import (
    SetupPrStatus,
    add_bodhiorchard_gitignore,
    add_prepare_script,
    append_bodhiorchard_claude_instructions,
    commit_and_push_setup_worktree,
    create_setup_pr,
    ensure_repo_worktrees,
    init_bodhiorchard_mcp_in_repo,
    install_claude_hooks,
    install_hooks,
    mark_setup_branch_pushed,
    prepare_setup_worktree,
)
from app.services.scan_progress import update_scan_progress

logger = structlog.get_logger(__name__)


async def phase_b1_repo_setup(
    db: AsyncSession,
    org_id: uuid.UUID,
    repo_path: str,
    repo_name: str,
    tracked_repo: TrackedRepository | None,
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
    setup_pr_message: str | None = None

    try:
        await update_scan_progress(
            scan_id,
            status="setting_up_worktrees",
            progress_pct=base_pct + 18,
        )
        main_wt, develop_wt = await ensure_repo_worktrees(repo_path)
        del main_wt, develop_wt  # paths consumed by the worktree-aware tools below

        # Persist detected branches + GitHub remote to tracked_repositories.
        # ``github_repo_full_name`` is needed by ``create_setup_pr`` to
        # decide whether the repo is on GitHub (and therefore a PR can be
        # opened). Local-pick adds skip this on POST /repos, so we
        # back-fill it here on the next scan.
        if tracked_repo:
            if tracked_repo.main_branch is None:
                detected_main = await _detect_main_branch(repo_path)
                if detected_main:
                    tracked_repo.main_branch = detected_main
            if tracked_repo.develop_branch is None:
                detected_dev = await _detect_develop_branch(repo_path)
                if detected_dev:
                    tracked_repo.develop_branch = detected_dev
            if not tracked_repo.github_repo_full_name:
                detected_full_name = await get_github_repo_full_name(repo_path)
                if detected_full_name:
                    tracked_repo.github_repo_full_name = detected_full_name
                    logger.info(
                        "tracked_repo_github_full_name_detected",
                        repo=repo_name,
                        full_name=detected_full_name,
                    )

        # All setup-file writes target a clean worktree at
        # ``<repo>/.bodhiorchard/setup-work`` checked out from
        # ``origin/<base>`` and switched onto ``bodhiorchard/init-setup``.
        # Doing the work here (rather than the cloned repo's main
        # checkout) keeps the user's working tree untouched and avoids
        # the stash/merge dance — which previously left repos with
        # non-``main`` defaults in a half-merged state and broke ingest
        # downstream.
        base = tracked_repo.main_branch if tracked_repo and tracked_repo.main_branch else "main"
        work_path = await prepare_setup_worktree(repo_path, base)
        if work_path is None:
            logger.warning(
                "scan_repo_setup_worktree_unavailable",
                scan_id=scan_id,
                repo=repo_name,
                base=base,
            )
            return setup_pr_message

        # Init Bodhiorchard MCP in repo (skips if already configured)
        await update_scan_progress(
            scan_id,
            status="setting_up_mcp",
            progress_pct=base_pct + 22,
        )
        mcp_changed = await init_bodhiorchard_mcp_in_repo(
            work_path,
            app_settings.public_url,
        )

        # Install git hooks to .githooks/ + set core.hooksPath
        await update_scan_progress(
            scan_id,
            status="installing_hooks",
            progress_pct=base_pct + 25,
        )
        hooks_changed = await install_hooks(work_path, app_settings.public_url, str(org_id))

        # Install Claude Code hooks (.claude/hooks/ + settings.json)
        claude_hooks_changed = await install_claude_hooks(
            work_path,
            app_settings.public_url,
        )

        # Ensure hooks are active regardless of commit/push status
        await run_git(["config", "core.hooksPath", ".githooks"], cwd=work_path)

        # Add .bodhiorchard/ to .gitignore
        gitignore_changed = add_bodhiorchard_gitignore(work_path)

        # Add prepare script to package.json
        prepare_changed = add_prepare_script(work_path)

        # Add Bodhiorchard workflow instructions to CLAUDE.md
        claude_md_changed = append_bodhiorchard_claude_instructions(work_path)

        # Branch, commit, push setup files, and create PR
        any_changed = (
            mcp_changed
            or hooks_changed
            or claude_hooks_changed
            or gitignore_changed
            or prepare_changed
            or claude_md_changed
        )
        pushed_branch: str | None = None
        if any_changed:
            await update_scan_progress(
                scan_id,
                status="pushing_setup",
                progress_pct=base_pct + 28,
            )
            pushed_branch = await commit_and_push_setup_worktree(work_path)
            if pushed_branch and tracked_repo is not None:
                # Stamp branch-pushed even when the App isn't configured —
                # this is what powers the amber "Open PR on GitHub" chip on
                # the row, and survives the ``create_setup_pr`` outcome.
                mark_setup_branch_pushed(tracked_repo)
                logger.info(
                    "bodhiorchard_setup_branch_pushed",
                    repo=repo_name,
                    branch=pushed_branch,
                )

        # Attempt to open / adopt the setup PR when:
        #   1. We just pushed (any_changed branch above), OR
        #   2. A previous scan pushed the branch (setup_branch_pushed_at is
        #      stamped) but no PR has been recorded yet (setup_pr_url is
        #      null) — typical when the GitHub App was connected after
        #      the first scan, or the installation_id wasn't yet
        #      auto-detectable on the first attempt.
        needs_pr_attempt = pushed_branch is not None or (
            tracked_repo is not None
            and tracked_repo.setup_branch_pushed_at is not None
            and tracked_repo.setup_pr_url is None
        )
        if needs_pr_attempt and tracked_repo is not None:
            org = await db.get(Organization, org_id)
            if org is not None:
                outcome = await create_setup_pr(
                    db,
                    org,
                    tracked_repo,
                    base,
                )
                branch_label = pushed_branch or "bodhiorchard/init-setup"
                if outcome.status == SetupPrStatus.MANUAL_REQUIRED:
                    compare_hint = outcome.compare_url or branch_label
                    setup_pr_message = (
                        f"Setup branch '{branch_label}' is on {repo_name}'s "
                        "remote. GitHub App not connected (or not installed "
                        "on this repo) — open the PR manually: "
                        f"{compare_hint}"
                    )
                elif outcome.status == SetupPrStatus.FAILED:
                    setup_pr_message = (
                        f"Setup branch '{branch_label}' is on {repo_name}'s "
                        "remote, but the GitHub App could not open the PR. "
                        "Check the App's installation permissions and "
                        "re-run the scan."
                    )

        if any_changed:
            await db.flush()
    except Exception:
        logger.exception(
            "scan_repo_setup_failed",
            scan_id=scan_id,
            repo=repo_name,
        )

    return setup_pr_message
