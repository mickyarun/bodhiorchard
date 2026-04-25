# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Background scan pipeline orchestrator.

Coordinates all scan phases (A→G): change detection, GitNexus indexing,
feature synthesis via Claude Code, cross-repo merge, skill analysis,
embedding generation, and config persistence.

Phase implementations live in ``scan_phases.py``; reusable helpers
(timing, upsert, embedding) live in ``scan_helpers.py``.
"""

import uuid

import structlog

from app.repositories.knowledge_item import KnowledgeItemRepository
from app.repositories.organization import OrganizationRepository
from app.repositories.user import UserRepository
from app.scan.prompts import (
    build_direct_scan_prompt,
    build_merge_prompt,
    build_synthesis_prompt,
)
from app.scan.soft_delete import (
    rollback_soft_deleted_features,
    soft_delete_for_changed_repos,
)
from app.services.gitnexus_indexer import GitNexusNotInstalledError
from app.services.scan_helpers import PhaseTimer, embed_missing_items
from app.services.scan_phases import (
    phase_b2_synthesis,
    phase_b3_merge,
    phase_e2_skill_remap,
    phase_g_persist,
)
from app.services.scan_progress import update_scan_progress
from app.services.scan_repo_loop import process_one_repo

logger = structlog.get_logger(__name__)

# Prompt builders re-exported here so legacy imports inside phase
# modules (`from app.services.scan_pipeline import build_synthesis_prompt`)
# keep resolving without a churn-heavy rename across call sites.
__all__ = [
    "build_direct_scan_prompt",
    "build_merge_prompt",
    "build_synthesis_prompt",
    "run_scan_pipeline",
]

# If >30% of tracked files changed, fall back to full scan
INCREMENTAL_THRESHOLD = 0.30

# ─── Progress-percentage budget ────────────────────────────────────────────
# The scan progress bar reserves 0..REPO_WINDOW_START for pre-repo setup,
# REPO_WINDOW_START..REPO_WINDOW_END for per-repo phases (shared across N
# repos), and REPO_WINDOW_END..100 for post-repo phases (merge, skills,
# persist). PER_REPO_OFFSET_MAX must be ≥ the largest ``base_pct + X``
# literal anywhere in this file or scan_phases.py — a unit test enforces
# this invariant (tests/services/test_scan_pipeline_progress.py).
REPO_WINDOW_START = 5
REPO_WINDOW_END = 60
PER_REPO_OFFSET_MAX = 52


def _repo_base_pct(repo_idx: int, total_repos: int) -> int:
    """Starting pct for a repo so ``base_pct + PER_REPO_OFFSET_MAX`` stays
    within the per-repo window regardless of ``total_repos``.

    For 1 repo: step=0 (base_pct stays at REPO_WINDOW_START).
    For N repos: last base_pct = REPO_WINDOW_END - PER_REPO_OFFSET_MAX, so
    the max per-repo pct lands exactly on REPO_WINDOW_END.
    """
    max_base = max(REPO_WINDOW_END - PER_REPO_OFFSET_MAX, REPO_WINDOW_START)
    step = (max_base - REPO_WINDOW_START) / max(total_repos - 1, 1) if total_repos > 1 else 0
    return int(REPO_WINDOW_START + repo_idx * step)


# Max features per LLM merge call (configurable via LLM_MERGE_BATCH_SIZE env)
def get_merge_batch_size() -> int:
    """Return the max features per LLM merge call from config."""
    from app.config import settings

    return settings.llm.merge_batch_size


async def run_scan_pipeline(
    scan_id: str,
    org_id: uuid.UUID,
    repo_paths: list[str],
    full_rescan: bool,
    user_id: str | None = None,
) -> None:
    """Execute the scan pipeline as a background task.

    Supports both single-repo and workspace (multi-repo) modes.
    For workspaces, each repo is scanned sequentially and results are aggregated.

    Phases per repo:
        A. Determine scan mode (incremental vs full)
        B. GitNexus indexing → knowledge_items (clusters)
        B1. Worktrees, MCP init, hooks, .gitignore, commit+push+PR
        D. Stale reference cleanup (incremental only)
        E. Git skill analysis → skill_profiles
        E1b. Auto-extract design system (if design files detected)
    Then globally:
        B2. Feature synthesis via Claude Code
        E2. Re-run skill analysis with feature-based modules
        B3. Cross-repo feature merge (workspace only)
        F. Embedding generation for items missing embeddings
        G. Save last_commit_sha per repo to org config

    Args:
        scan_id: Unique scan identifier for status tracking.
        org_id: Organization UUID.
        repo_paths: List of absolute paths to git repositories to scan.
        full_rescan: Whether to force a complete rescan.
        user_id: Optional user ID for sending completion notifications.
    """
    from app.database import AsyncSessionLocal

    is_workspace = len(repo_paths) > 1
    timer = PhaseTimer(scan_id)
    soft_deleted_ids: list[uuid.UUID] = []

    try:
        async with AsyncSessionLocal() as db:
            org_repo = OrganizationRepository(db)
            org = await org_repo.get_by_id(org_id)
            config = dict(org.config or {})
            scan_cfg = config.get("scan", {})

            total_features_synthesized = 0
            total_profiles = 0
            _pending_synthesis: list[dict] = []
            total_stale = 0
            all_unmatched: list[str] = []
            overall_mode = "full"
            new_shas: dict[str, str] = {}

            user_repo = UserRepository(db)
            email_to_user = await user_repo.get_email_map(org_id)

            # Load tracked repo records for SHA lookup and post-scan updates
            from app.repositories.tracked_repository import TrackedRepoRepository

            tracked_repo_repo = TrackedRepoRepository(db, org_id=org_id)

            # Soft-delete scoped to repos whose HEAD SHA actually changed
            # since the last scan. Unchanged repos keep their feature
            # rows live through the whole scan — a full-rescan of an org
            # where only one repo has changes no longer dirties every
            # repo's features. See §D.7 of the plan.
            ki_repo = KnowledgeItemRepository(db, org_id=org_id)
            if full_rescan or not config.get("knowledge", {}).get("last_commit_sha"):
                soft_deleted_ids = await soft_delete_for_changed_repos(
                    db,
                    org_id=org_id,
                    repo_paths=repo_paths,
                    tracked_repo_repo=tracked_repo_repo,
                    full_rescan=full_rescan,
                )
                await db.flush()
                if soft_deleted_ids:
                    logger.info(
                        "scan_soft_deleted_features",
                        scan_id=scan_id,
                        deactivated=len(soft_deleted_ids),
                    )

            scan_uuid = uuid.UUID(scan_id)

            for repo_idx, repo_path in enumerate(repo_paths):
                base_pct = _repo_base_pct(repo_idx, len(repo_paths))
                repo_result = await process_one_repo(
                    db=db,
                    org_id=org_id,
                    scan_id=scan_id,
                    scan_uuid=scan_uuid,
                    repo_idx=repo_idx,
                    total_repos=len(repo_paths),
                    is_workspace=is_workspace,
                    repo_path=repo_path,
                    base_pct=base_pct,
                    full_rescan=full_rescan,
                    config=config,
                    scan_cfg=scan_cfg,
                    timer=timer,
                    tracked_repo_repo=tracked_repo_repo,
                    ki_repo=ki_repo,
                    email_to_user=email_to_user,
                )
                if repo_result.is_incremental:
                    overall_mode = "incremental"
                if repo_result.head_sha:
                    new_shas[repo_path] = repo_result.head_sha
                total_stale += repo_result.stale_cleaned
                total_profiles += repo_result.profiles_added
                all_unmatched.extend(
                    e for e in repo_result.unmatched_emails if e not in all_unmatched
                )
                if repo_result.pending_synthesis is not None:
                    _pending_synthesis.append(repo_result.pending_synthesis)

            # Global-phase wrapper: each FEATURE_SYNTHESIS / SKILL_REMAP /
            # FEATURE_MERGE / EMBEDDING_BACKFILL / PERSIST_RESULTS call
            # is checkpoint-gated with ``repo_id=None`` so resume can
            # skip completed ones and retry failed ones. Without this
            # wrap, the per-phase checkpoint table would be empty for
            # the entire global stripe and the UI timeline would render
            # zero rows for everything after the per-repo phases.
            #
            # State-recovery invariant: downstream phases must not
            # depend on ``nonlocal`` side-effects set inside the phase
            # body, because on a resume the body is skipped. After each
            # global phase we re-derive any state the next phase needs
            # from the DB — the source of truth — rather than trusting
            # an assignment that may never have run.
            from collections.abc import Awaitable, Callable
            from typing import Any

            from app.models.scan_phase import ScanPhase as _ScanPhase
            from app.services.scan_checkpoints import (
                PhaseRunOutcome,
                run_checkpointed_phase,
            )

            async def _global_phase(
                phase: _ScanPhase,
                fn: Callable[[], Awaitable[dict[str, Any]]],
            ) -> PhaseRunOutcome:
                return await run_checkpointed_phase(
                    db=db,
                    scan_id=scan_uuid,
                    org_id=org_id,
                    phase=phase,
                    phase_fn=fn,
                    repo_id=None,
                )

            # --- Phase B2: Parallel feature synthesis via Claude Code ---
            timer.start()

            async def _run_b2() -> dict[str, Any]:
                # phase_b2_synthesis returns an int from ki_repo.count_active,
                # but that value can under-report if B2 runs partially and
                # crashes — the subsequent re-derive after this phase uses
                # the live DB count anyway, so we stamp the same
                # authoritative count into the payload for UI fidelity
                # on resumed runs where the body is skipped.
                await phase_b2_synthesis(
                    db,
                    org_id,
                    _pending_synthesis,
                    is_workspace,
                    scan_cfg,
                    scan_id,
                    ki_repo,
                )
                count = await ki_repo.count_active(category="feature_registry")
                return {"features_synthesized": count}

            await _global_phase(_ScanPhase.FEATURE_SYNTHESIS, _run_b2)
            # Re-derive from DB: on resume the body skipped, nonlocal
            # wouldn't fire, so read the authoritative count of
            # scan-sourced feature rows.
            total_features_synthesized = await ki_repo.count_active(category="feature_registry")
            timer.mark("B2_synthesis_parallel")

            # --- Phase B3: Cross-repo merge + embedding + dedup ---
            # Must run BEFORE E2 so skill remap uses merged feature names.
            timer.start()

            async def _run_b3() -> dict[str, Any]:
                # phase_b3_merge mutates organizations.config (inside its
                # own nested transaction). The post-wrapper re-read from
                # DB is the single source of truth for the local ``config``
                # dict, so no nonlocal assignment is needed here.
                await phase_b3_merge(
                    db,
                    org_id,
                    repo_paths,
                    is_workspace,
                    total_features_synthesized,
                    scan_cfg,
                    scan_id,
                    ki_repo,
                )
                return {}

            await _global_phase(_ScanPhase.FEATURE_MERGE, _run_b3)
            # Re-derive config from DB: merge may have mutated
            # ``organizations.config`` and on resume our local ``config``
            # dict would otherwise be stale.
            org = await org_repo.get_by_id(org_id)
            if org is not None and org.config:
                config = dict(org.config)
            timer.mark("B3_merge")

            # --- Phase E2: Re-run skill analysis with merged feature names ---
            if _pending_synthesis and total_features_synthesized > 0:
                timer.start()

                async def _run_e2() -> dict[str, Any]:
                    e2_profiles = await phase_e2_skill_remap(
                        db,
                        org_id,
                        repo_paths,
                        email_to_user,
                        scan_id,
                    )
                    return {"profiles": e2_profiles}

                e2_outcome = await _global_phase(_ScanPhase.SKILL_REMAP, _run_e2)
                e2_profiles_from_checkpoint = e2_outcome.payload.get("profiles", 0)
                if e2_profiles_from_checkpoint:
                    total_profiles = e2_profiles_from_checkpoint
                timer.mark("E2_skill_remap")

            # Synthesis + merge succeeded — hard-delete only the features that
            # were soft-deleted at scan start and not reactivated by synthesis.
            if soft_deleted_ids:
                purged = await ki_repo.delete_inactive_by_ids(soft_deleted_ids)
                if purged:
                    await db.flush()
                    logger.info("scan_purged_stale_features", scan_id=scan_id, purged=purged)

            # --- Phase F: Embed any items still missing embeddings ---
            # Runs before G so the persisted feature_count is accurate.
            await update_scan_progress(scan_id, status="finalizing", progress_pct=93)

            async def _run_f() -> dict[str, Any]:
                final_embedded = await embed_missing_items(db, org_id)
                if final_embedded:
                    logger.info("scan_final_embed_pass", scan_id=scan_id, embedded=final_embedded)
                return {"embedded": final_embedded}

            await _global_phase(_ScanPhase.EMBEDDING_BACKFILL, _run_f)

            # --- Phase G: Save last commit SHAs + scan results ---
            timer.start()
            await update_scan_progress(
                scan_id,
                status="saving_results",
                progress_pct=96,
            )

            async def _run_g() -> dict[str, Any]:
                count = await phase_g_persist(
                    db,
                    org_id,
                    repo_paths,
                    new_shas,
                    config,
                    total_profiles,
                    all_unmatched,
                    overall_mode,
                    ki_repo,
                )
                return {"actual_features": count}

            g_outcome = await _global_phase(_ScanPhase.PERSIST_RESULTS, _run_g)
            # Always prefer the checkpoint payload — it holds the count
            # whether this run executed G or copied a DONE row from
            # an earlier scan. Falls back to a fresh DB count if the
            # payload is somehow empty (e.g. a legacy DONE checkpoint
            # written before this field existed).
            actual_features = g_outcome.payload.get("actual_features")
            if actual_features is None:
                actual_features = await ki_repo.count_active(category="feature_registry")
            timer.mark("G_persist")

            # Cross-phase audit. Each phase's in-line guards already raise
            # for the failure modes they own (orphan features, unvisited
            # merges, unmatched authors). The audit catches signals that
            # are only visible end-to-end — most importantly, repos that
            # GitNexus indexed but produced zero synthesized_features
            # (the Bug A early-warning). Warn-only by design: a clean
            # scan can legitimately produce zero features for a repo
            # whose clusters were all infrastructure.
            from app.scan.audit import audit_scan
            from app.scan.context import ScanContext as _ScanContextDC

            audit_report = await audit_scan(
                _ScanContextDC(scan_id=scan_uuid, org_id=org_id),
            )
            if audit_report.missing_repo_synth:
                logger.warning(
                    "scan_audit_missing_repo_synth",
                    scan_id=scan_id,
                    repos=[
                        {
                            "name": a.repo_name,
                            "clusters": a.cluster_count,
                            "synth": a.synth_count,
                        }
                        for a in audit_report.missing_repo_synth
                    ],
                )
            if audit_report.orphan_features:
                logger.warning(
                    "scan_audit_orphan_features",
                    scan_id=scan_id,
                    count=len(audit_report.orphan_features),
                )

            await update_scan_progress(
                scan_id,
                status="completed",
                progress_pct=100,
                features_indexed=actual_features,
                profiles_found=total_profiles,
                stale_cleaned=total_stale,
                unmatched_authors=all_unmatched[:20],
                scan_mode=overall_mode,
            )

            logger.info(
                "scan_complete",
                scan_id=scan_id,
                repos=len(repo_paths),
                mode=overall_mode,
                features=actual_features,
                profiles=total_profiles,
                unmatched=len(all_unmatched),
                phase_timings=timer.timings,
            )

            if user_id:
                from app.services.notification_service import send_scan_notification

                send_scan_notification(
                    scan_id=scan_id,
                    user_id=user_id,
                    org_id=str(org_id),
                    completed=True,
                    features_indexed=actual_features,
                    profiles_found=total_profiles,
                )

    except GitNexusNotInstalledError as exc:
        logger.error("scan_gitnexus_not_installed", scan_id=scan_id, error=str(exc))
        await update_scan_progress(scan_id, status="failed", error=str(exc))
        await rollback_soft_deleted_features(org_id, scan_id, soft_deleted_ids)
        if user_id:
            from app.services.notification_service import send_scan_notification

            send_scan_notification(
                scan_id=scan_id,
                user_id=user_id,
                org_id=str(org_id),
                completed=False,
                error_message=str(exc),
            )
    except Exception as exc:
        logger.exception("scan_pipeline_error", scan_id=scan_id)
        await update_scan_progress(scan_id, status="failed", error=str(exc)[:500])
        await rollback_soft_deleted_features(org_id, scan_id, soft_deleted_ids)
        if user_id:
            from app.services.notification_service import send_scan_notification

            send_scan_notification(
                scan_id=scan_id,
                user_id=user_id,
                org_id=str(org_id),
                completed=False,
                error_message=str(exc)[:500],
            )
