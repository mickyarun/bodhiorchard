# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Per-repo phase stripe for the scan pipeline.

Extracted from ``scan_pipeline.py`` so that:

1. The orchestrator in ``scan_pipeline.py`` stays focused on session
   set-up, soft-delete policy, and the global (post-repo) phases.
2. Every per-repo phase can be wrapped in ``run_checkpointed_phase``
   without inflating the orchestrator beyond the file-size gate.

The per-repo stripe covers phases ``MODE_DETECTION`` → ``GITNEXUS_INDEX``
→ ``REPO_SETUP`` → (``STALE_CLEANUP`` if incremental) → ``SKILL_EXTRACTION``
→ ``DESIGN_SYSTEM_EXTRACT``. Everything after that is global and remains
in the orchestrator.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scan_phase import ScanPhase
from app.repositories.knowledge_item import KnowledgeItemRepository
from app.repositories.tracked_repository import TrackedRepoRepository
from app.services.git_analyzer import analyze_repo_skills, get_head_sha
from app.services.git_operations import (
    create_scan_worktree,
    get_github_repo_full_name,
    remove_scan_worktree,
)
from app.services.gitnexus_indexer import index_repo_with_gitnexus
from app.services.scan_checkpoints import UnmatchedAuthorsError, run_checkpointed_phase
from app.services.scan_design_system import maybe_extract_design_system
from app.services.scan_helpers import (
    PhaseTimer,
    cleanup_stale_references,
    load_feature_map,
)
from app.services.scan_phases import (
    phase_a_scan_mode,
    phase_b1_repo_setup,
    phase_e_skills,
)
from app.services.scan_progress import append_repo_warning, update_scan_progress
from app.services.scan_synthesis_queue import build_pending_synthesis

logger = structlog.get_logger(__name__)


@dataclass
class RepoLoopResult:
    """Outcomes a single repo's stripe contributes to the global aggregate."""

    is_incremental: bool = False
    setup_pr_msg: str | None = None
    head_sha: str | None = None
    stale_cleaned: int = 0
    profiles_added: int = 0
    unmatched_emails: list[str] = field(default_factory=list)
    pending_synthesis: dict[str, Any] | None = None


async def process_one_repo(
    *,
    db: AsyncSession,
    org_id: uuid.UUID,
    scan_id: str,
    scan_uuid: uuid.UUID,
    repo_idx: int,
    total_repos: int,
    is_workspace: bool,
    repo_path: str,
    base_pct: int,
    full_rescan: bool,
    config: dict[str, Any],
    scan_cfg: dict[str, Any],
    timer: PhaseTimer,
    tracked_repo_repo: TrackedRepoRepository,
    ki_repo: KnowledgeItemRepository,
    email_to_user: dict[str, Any],
) -> RepoLoopResult:
    """Run the per-repo phase stripe for one repository.

    Each phase runs through ``run_checkpointed_phase`` in observe-only
    mode — ``skip_if_done`` and ``reuse_across_scans`` are both False
    so this layer only records checkpoints without changing pipeline
    behaviour. P5 flips both flags on.

    Args:
        email_to_user: Mutated in-place as ``phase_e_skills`` resolves
            new author emails, so subsequent repos reuse the mapping.

    Returns:
        A ``RepoLoopResult`` carrying the values the orchestrator
        accumulates across the workspace.
    """
    repo_name = Path(repo_path).name
    if is_workspace:
        logger.info(
            "scan_workspace_repo",
            scan_id=scan_id,
            repo=repo_name,
            index=repo_idx + 1,
            total=total_repos,
        )

    tracked_repo = await tracked_repo_repo.get_by_path(repo_path)

    # Auto-populate GitHub repo name from git remote if missing. Not a
    # checkpointed phase — it's trivial housekeeping that must succeed
    # before any phase runs (the synthesis queue uses ``repo.name``).
    if tracked_repo is not None and not tracked_repo.github_repo_full_name:
        gh_name = await get_github_repo_full_name(repo_path)
        if gh_name:
            tracked_repo.github_repo_full_name = gh_name
            await db.flush()

    main_branch = (tracked_repo.main_branch if tracked_repo else None) or "main"
    repo_id_for_ckpt = tracked_repo.id if tracked_repo else None

    await update_scan_progress(scan_id, status="checking_out", progress_pct=base_pct)
    try:
        scan_path = await create_scan_worktree(repo_path, main_branch)
    except RuntimeError:
        logger.warning(
            "scan_worktree_failed_using_repo",
            scan_id=scan_id,
            repo=repo_name,
        )
        scan_path = repo_path  # fall back to scanning the live tree

    # Capture the current HEAD SHA once, up-front. SHA-reusable phases
    # (GitNexus index, skill extraction, design-system extract) pass
    # this to the checkpoint wrapper so a later scan can reuse their
    # payload when the repo is unchanged — see ``SHA_REUSABLE_PHASES``.
    current_sha = await get_head_sha(scan_path)

    # Checkpoint wrapper: binds pipeline context so each phase call
    # site stays one line. ``sha`` flows through to ``run_checkpointed_phase``;
    # its internal check against ``SHA_REUSABLE_PHASES`` decides whether
    # to actually attempt cross-scan reuse, so we can pass the same value
    # for every phase without leaking the reuse policy here.
    async def _ckpt(
        phase: ScanPhase,
        phase_fn: Callable[[], Awaitable[dict[str, Any]]],
    ) -> None:
        await run_checkpointed_phase(
            db=db,
            scan_id=scan_uuid,
            org_id=org_id,
            phase=phase,
            phase_fn=phase_fn,
            repo_id=repo_id_for_ckpt,
            sha=current_sha,
        )

    result = RepoLoopResult()
    deleted_files: list[str] = []
    gitnexus_features: list[Any] = []
    gitnexus_overview: str = ""
    gitnexus_success = False

    try:
        # --- Phase A: MODE_DETECTION -----------------------------------

        async def _run_mode_detection() -> dict[str, Any]:
            nonlocal deleted_files
            timer.start()
            await update_scan_progress(
                scan_id, status="analyzing_changes", progress_pct=base_pct + 5
            )
            last_sha = tracked_repo.head_sha if tracked_repo else None
            if not last_sha:
                knowledge_cfg = config.get("knowledge") or {}
                last_sha = knowledge_cfg.get("repo_shas", {}).get(repo_path) or knowledge_cfg.get(
                    "last_commit_sha"
                )

            is_incr, _repo_full_rescan, dfiles = await phase_a_scan_mode(
                db,
                org_id,
                repo_path,
                repo_name,
                full_rescan,
                last_sha,
                ki_repo,
                scan_id,
            )
            result.is_incremental = is_incr
            deleted_files = list(dfiles or [])
            timer.mark(f"A_scan_mode/{repo_name}")
            return {
                "mode": "incremental" if is_incr else "full",
                "deleted_count": len(deleted_files),
                "last_sha": last_sha,
            }

        await _ckpt(ScanPhase.MODE_DETECTION, _run_mode_detection)

        # --- Phase B: GITNEXUS_INDEX -----------------------------------

        async def _run_gitnexus_index() -> dict[str, Any]:
            nonlocal gitnexus_features, gitnexus_overview, gitnexus_success
            timer.start()
            await update_scan_progress(scan_id, status="indexing_code", progress_pct=base_pct + 10)
            gn = await index_repo_with_gitnexus(repo_path, force=not result.is_incremental)
            gitnexus_success = gn.success
            gitnexus_features = list(gn.features or [])
            gitnexus_overview = gn.repo_overview or ""
            if gn.success:
                from app.services.claude_runner import ensure_gitnexus_mcp

                await update_scan_progress(
                    scan_id,
                    status="setting_up_gitnexus",
                    progress_pct=base_pct + 15,
                )
                await ensure_gitnexus_mcp()
            elif gn.error:
                await append_repo_warning(
                    scan_id,
                    repo=repo_name,
                    phase="indexing_code",
                    summary=gn.error,
                    hint=gn.error_hint,
                )
            await db.flush()
            timer.mark(f"B_gitnexus/{repo_name}")
            return {
                "success": gn.success,
                "feature_count": len(gitnexus_features),
                "error": gn.error,
            }

        await _ckpt(ScanPhase.GITNEXUS_INDEX, _run_gitnexus_index)

        # --- Phase B1: REPO_SETUP --------------------------------------

        async def _run_repo_setup() -> dict[str, Any]:
            timer.start()
            pr_msg = await phase_b1_repo_setup(
                db,
                org_id,
                repo_path,
                repo_name,
                tracked_repo,
                scan_id,
                base_pct,
            )
            if pr_msg:
                result.setup_pr_msg = pr_msg
                await update_scan_progress(scan_id, setup_pr_message=pr_msg)
            timer.mark(f"B1_repo_setup/{repo_name}")
            return {"setup_pr_message_set": pr_msg is not None}

        await _ckpt(ScanPhase.REPO_SETUP, _run_repo_setup)

        # Synthesis-queue prep is NOT checkpointed — the checkpoint lives
        # on the later global FEATURE_SYNTHESIS phase.
        result.pending_synthesis = await build_pending_synthesis(
            repo_name=repo_name,
            repo_path=repo_path,
            repo_id=repo_id_for_ckpt,
            org_id=org_id,
            is_incremental=result.is_incremental,
            gitnexus_success=gitnexus_success,
            gitnexus_features=gitnexus_features,
            gitnexus_overview=gitnexus_overview,
        )

        # --- Phase D: STALE_CLEANUP (incremental only) ----------------
        if result.is_incremental and deleted_files:

            async def _run_stale_cleanup() -> dict[str, Any]:
                timer.start()
                await update_scan_progress(
                    scan_id, status="cleaning_stale", progress_pct=base_pct + 32
                )
                cleaned = await cleanup_stale_references(db, org_id, deleted_files)
                result.stale_cleaned = cleaned
                await db.flush()
                timer.mark(f"D_stale_cleanup/{repo_name}")
                return {"stale_cleaned": cleaned}

            await _ckpt(ScanPhase.STALE_CLEANUP, _run_stale_cleanup)

        # --- Phase E: SKILL_EXTRACTION --------------------------------

        async def _run_skill_extraction() -> dict[str, Any]:
            timer.start()
            await update_scan_progress(
                scan_id, status="analyzing_skills", progress_pct=base_pct + 38
            )
            feature_map = await load_feature_map(db, org_id)
            skill_entries = await analyze_repo_skills(scan_path, feature_map=feature_map or None)
            profiles, unmatched = await phase_e_skills(
                db,
                org_id,
                repo_path,
                skill_entries,
                email_to_user,
                scan_cfg,
            )
            result.profiles_added += profiles
            for email in unmatched:
                if email not in result.unmatched_emails:
                    result.unmatched_emails.append(email)
            timer.mark(f"E_skills/{repo_name}")
            # Halt the scan on unmatched authors so the per-repo retry
            # endpoint becomes the recovery path: the user adds an alias
            # / creates the member, then re-runs just this phase. The
            # matched profiles already inserted in this transaction roll
            # back with the outer pipeline session — retry's upserts are
            # idempotent so no duplicates land.
            if unmatched:
                raise UnmatchedAuthorsError(unmatched, repo_name)
            return {
                "profiles_added": profiles,
                "unmatched_count": len(unmatched),
                "entry_count": len(skill_entries),
            }

        await _ckpt(ScanPhase.SKILL_EXTRACTION, _run_skill_extraction)

        # --- Phase E1b: DESIGN_SYSTEM_EXTRACT -------------------------

        async def _run_design_system_extract() -> dict[str, Any]:
            timer.start()
            await update_scan_progress(
                scan_id,
                status="extracting_design_system",
                progress_pct=base_pct + 48,
            )
            try:
                await maybe_extract_design_system(db, org_id, scan_path, tracked_repo, full_rescan)
            except Exception:
                # Design-system extraction is enqueued async and must not
                # sink the whole scan. Record the issue and keep moving.
                logger.exception(
                    "design_system_auto_extract_failed",
                    scan_id=scan_id,
                    repo=repo_name,
                )
            timer.mark(f"E1b_design_system/{repo_name}")
            return {}

        await _ckpt(ScanPhase.DESIGN_SYSTEM_EXTRACT, _run_design_system_extract)

        # Record HEAD SHA so the later global persist phase can save it.
        # We captured ``current_sha`` once up-front; reusing it here avoids
        # a redundant ``git rev-parse`` and keeps the SHA we recorded on
        # each checkpoint in sync with the one that lands in the persist
        # phase's ``repo_shas`` map.
        await update_scan_progress(scan_id, status="finalizing_repo", progress_pct=base_pct + 52)
        result.head_sha = current_sha
    finally:
        await remove_scan_worktree(repo_path)

    return result
