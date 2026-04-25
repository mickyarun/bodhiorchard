# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Admin endpoints for resuming, retrying, recovering, and resetting scans.

Six routes live here — all scoped to ``org:edit_settings`` and all
operating on the ``scan_phase_checkpoints`` + ``synthesized_features``
tables introduced in P1:

- ``GET  /scan/latest`` — return the org's most recent scan (any
  status) enriched with phases. Replaces the frontend's localStorage
  dance with a single authoritative query.
- ``GET  /scan/{scan_id}/checkpoints`` — list every checkpoint for a
  scan so the frontend timeline has authoritative data.
- ``POST /scan/{scan_id}/resume`` — mint a child scan that inherits
  the parent's DONE / SKIPPED checkpoints and re-runs everything else.
- ``POST /scan/{scan_id}/phases/{phase}/retry`` — same as resume, but
  the child scan deliberately omits the specified phase's checkpoint
  so that phase runs fresh. Optional ``?repo_id=`` narrows the retry
  to one per-repo row.
- ``POST /scan/recover/feature/{synth_feature_id}`` — read the immutable
  pre-merge row from ``synthesized_features`` and restore the feature
  in ``knowledge_items`` + ``knowledge_to_repo`` without rerunning the
  scan. Used to roll back a bad merge surgically.
- ``POST /scan/reset`` — hard-wipe every scan-sourced feature + skill
  profile for the org, clear per-repo ``head_sha``, and kick off a
  fresh full rescan. The escape hatch for "Full Rescan didn't clean
  up enough" or "resume / retry are both stuck".
"""

from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db, require_permissions
from app.models.knowledge_item import KnowledgeItem
from app.models.scan_phase import CheckpointStatus, ScanPhase
from app.models.scan_phase_checkpoint import ScanPhaseCheckpoint
from app.models.user import User
from app.repositories.knowledge_item import KnowledgeItemRepository
from app.repositories.organization import OrganizationRepository
from app.repositories.scan_phase_checkpoint import ScanPhaseCheckpointRepository
from app.repositories.skill_profile import SkillProfileRepository
from app.repositories.synthesized_feature import SynthesizedFeatureRepository
from app.repositories.tracked_repository import TrackedRepoRepository
from app.schemas.scan_recovery import (
    CheckpointListResponse,
    CheckpointRead,
    FeatureRecoveryResult,
    ResetIndexResponse,
    ResumeScanResponse,
    RetryPhaseResponse,
)
from app.schemas.skills import ScanStatus
from app.services.scan_pipeline import run_scan_pipeline
from app.services.scan_progress import (
    create_scan_progress,
    enrich_status_with_phases,
    get_active_scan_for_org,
    get_scan_progress,
)

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["scan-recovery"])


# ─── GET /scan/latest ────────────────────────────────────────────────


@router.get(
    "/scan/latest",
    response_model=ScanStatus | None,
    dependencies=[Depends(require_permissions("org:edit_settings"))],
)
async def get_latest_scan(
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ScanStatus | None:
    """Return the org's most recent scan, enriched with per-phase state.

    Covers any status (running / completed / failed / skipped) — the
    frontend inspects ``status`` and decides whether to attach a
    live tracker, show the Resume banner, or render nothing. 204 No
    Content when the org has never run a scan.

    The Redis progress hash ages out after 2 h. If the most recent
    checkpoint is older than that, we synthesise a minimal
    ``ScanStatus`` from the checkpoint rows so the timeline still
    renders — ``status`` / ``error`` / ``scan_id`` are enough for the
    failed-scan banner, and the enriched ``phases[]`` carries the
    timeline.
    """
    org = await OrganizationRepository(db).get_for_user(current_user)

    # Prefer a currently-active scan over the latest checkpoint: a scan
    # that just started (e.g. from /scan/reset) may not have written
    # any checkpoints yet, so ``get_latest_scan_id`` would still return
    # the *previous* terminal scan — leaving the UI stuck on old
    # failed-banner state even though a fresh scan is in flight.
    active = await get_active_scan_for_org(str(org.id))
    if active is not None:
        return await enrich_status_with_phases(db, org.id, active)

    ck_repo = ScanPhaseCheckpointRepository(db, org_id=org.id)
    latest_id = await ck_repo.get_latest_scan_id()
    if latest_id is None:
        response.status_code = status.HTTP_204_NO_CONTENT
        return None

    live = await get_scan_progress(str(latest_id))
    base_status = live or await _synthesize_status_from_checkpoints(latest_id, ck_repo)
    return await enrich_status_with_phases(db, org.id, base_status)


async def _synthesize_status_from_checkpoints(
    scan_id: uuid.UUID,
    ck_repo: ScanPhaseCheckpointRepository,
) -> ScanStatus:
    """Build a minimal ``ScanStatus`` from checkpoint rows alone.

    Called only when the Redis progress hash has aged out — e.g.
    for a scan that failed more than 2 h ago and that the user is
    now returning to. Conservative: only the fields the frontend
    needs to decide "failed banner vs nothing" are populated;
    the enrichment step adds ``phases[]`` on top.
    """
    rows = await ck_repo.list_for_scan(scan_id)
    statuses = {row.status for row in rows}

    if CheckpointStatus.FAILED in statuses:
        overall = "failed"
    elif _has_done_persist(rows):
        overall = "completed"
    elif statuses and statuses.issubset({CheckpointStatus.DONE, CheckpointStatus.SKIPPED}):
        # Every checkpoint terminal-done but no PERSIST_RESULTS — rare
        # transitional state (scan crashed between last phase and G).
        # Treat as failed so the UI invites a retry instead of showing a
        # false green.
        overall = "failed"
    else:
        overall = "running"

    error_msg: str | None = None
    for row in rows:
        if row.status is CheckpointStatus.FAILED and row.error_message:
            error_msg = row.error_message
            break

    return ScanStatus(
        scan_id=str(scan_id),
        status=overall,
        error=error_msg,
    )


def _has_done_persist(rows: list[ScanPhaseCheckpoint]) -> bool:
    """True when at least one PERSIST_RESULTS checkpoint is DONE."""
    return any(
        row.phase is ScanPhase.PERSIST_RESULTS and row.status is CheckpointStatus.DONE
        for row in rows
    )


# ─── GET /scan/{scan_id}/checkpoints ─────────────────────────────────


@router.get(
    "/scan/{scan_id}/checkpoints",
    response_model=CheckpointListResponse,
    dependencies=[Depends(require_permissions("org:edit_settings"))],
)
async def list_scan_checkpoints(
    scan_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CheckpointListResponse:
    """Return every checkpoint row for a scan.

    Powers the frontend timeline. Ordered by (created_at, phase,
    attempt) so per-repo rows cluster naturally and retry attempts
    show in chronological order.
    """
    org = await OrganizationRepository(db).get_for_user(current_user)
    ck_repo = ScanPhaseCheckpointRepository(db, org_id=org.id)
    rows = await ck_repo.list_for_scan(scan_id)
    return CheckpointListResponse(
        scan_id=scan_id,
        total=len(rows),
        checkpoints=[CheckpointRead.model_validate(row) for row in rows],
    )


# ─── POST /scan/{scan_id}/resume ─────────────────────────────────────


@router.post(
    "/scan/{scan_id}/resume",
    response_model=ResumeScanResponse,
    dependencies=[Depends(require_permissions("org:edit_settings"))],
)
async def resume_scan(
    scan_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ResumeScanResponse:
    """Mint a child scan that skips the parent's completed phases.

    The parent's DONE and SKIPPED checkpoints are copied forward so the
    child scan only actually re-executes phases that were FAILED /
    PENDING / RUNNING when the parent stopped. The pipeline's
    skip-if-done short-circuit (P5) does the rest.
    """
    org = await OrganizationRepository(db).get_for_user(current_user)
    await _assert_parent_scan_exists(db, org_id=org.id, parent_scan_id=scan_id)

    new_scan_id = uuid.uuid4()
    ck_repo = ScanPhaseCheckpointRepository(db, org_id=org.id)
    copied = await ck_repo.copy_terminal_from_parent(
        parent_scan_id=scan_id,
        new_scan_id=new_scan_id,
    )
    await db.commit()

    await _dispatch_scan(
        db,
        background_tasks,
        org_id=org.id,
        scan_id=new_scan_id,
        user=current_user,
        parent_scan_id=scan_id,
    )
    logger.info(
        "scan_resume_dispatched",
        parent_scan_id=str(scan_id),
        new_scan_id=str(new_scan_id),
        copied_checkpoints=copied,
    )
    return ResumeScanResponse(
        new_scan_id=new_scan_id,
        parent_scan_id=scan_id,
        copied_checkpoints=copied,
    )


# ─── POST /scan/{scan_id}/phases/{phase}/retry ───────────────────────


@router.post(
    "/scan/{scan_id}/phases/{phase}/retry",
    response_model=RetryPhaseResponse,
    dependencies=[Depends(require_permissions("org:edit_settings"))],
)
async def retry_scan_phase(
    scan_id: uuid.UUID,
    phase: ScanPhase,
    background_tasks: BackgroundTasks,
    repo_id: uuid.UUID | None = Query(
        None,
        description=(
            "For PER_REPO phases, narrow the retry to a single repo. "
            "When omitted, every repo's checkpoint for ``phase`` is "
            "excluded from the copy so that phase runs fresh for all."
        ),
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RetryPhaseResponse:
    """Mint a child scan where one phase's checkpoint is deliberately dropped.

    The copy-forward step excludes the specified (phase, optional
    repo_id); every other DONE / SKIPPED checkpoint is forwarded, so
    the pipeline re-runs *only* the targeted phase plus anything the
    parent left in FAILED state.
    """
    org = await OrganizationRepository(db).get_for_user(current_user)
    await _assert_parent_scan_exists(db, org_id=org.id, parent_scan_id=scan_id)

    new_scan_id = uuid.uuid4()
    ck_repo = ScanPhaseCheckpointRepository(db, org_id=org.id)
    copied = await ck_repo.copy_terminal_from_parent(
        parent_scan_id=scan_id,
        new_scan_id=new_scan_id,
        exclude_phase=phase,
        exclude_repo_id=repo_id,
    )
    await db.commit()

    await _dispatch_scan(
        db,
        background_tasks,
        org_id=org.id,
        scan_id=new_scan_id,
        user=current_user,
        parent_scan_id=scan_id,
    )
    logger.info(
        "scan_phase_retry_dispatched",
        parent_scan_id=str(scan_id),
        new_scan_id=str(new_scan_id),
        phase=phase.value,
        repo_id=str(repo_id) if repo_id else None,
        copied_checkpoints=copied,
    )
    return RetryPhaseResponse(
        new_scan_id=new_scan_id,
        parent_scan_id=scan_id,
        phase=phase.value,
        repo_id=repo_id,
        copied_checkpoints=copied,
    )


# ─── POST /scan/reset ────────────────────────────────────────────────


@router.post(
    "/scan/reset",
    response_model=ResetIndexResponse,
    dependencies=[Depends(require_permissions("org:edit_settings"))],
)
async def reset_index_and_rescan(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ResetIndexResponse:
    """Hard-wipe the scan-sourced index and kick off a fresh full rescan.

    This is the "something's wrong, start clean" escape hatch for when
    resume / retry aren't enough — e.g. a corrupted merge landed stable
    but wrong features, or the repo topology changed enough that
    incremental logic can't recover. The reset:

    1. Hard-deletes every ``feature_registry`` knowledge_item that was
       scan-sourced (BUD-authored features are preserved).
    2. Deletes every skill_profile for the org (they're all derived
       from scan-time git-log analysis — the next scan rebuilds them).
    3. Marks every ``synthesized_features`` row as superseded so the
       next synthesis pass sees a clean pre-merge view.
    4. Clears ``head_sha`` / ``last_scanned_at`` on every active
       tracked repo so ``phase_a_scan_mode`` treats each as a first
       run and forces the full pipeline.
    5. Dispatches ``run_scan_pipeline`` with ``full_rescan=True``.

    The returned ``new_scan_id`` is the scan the UI should immediately
    start tracking — no confirmation / interstitial needed; the
    frontend's existing dialog already walls the button off.
    """
    org = await OrganizationRepository(db).get_for_user(current_user)

    # Verify we have something to scan BEFORE destroying any existing
    # index — otherwise an org with no active repos would wipe every
    # feature and skill profile, then see the dispatch fail with 400
    # and have no way to rebuild.
    tr_repo = TrackedRepoRepository(db, org_id=org.id)
    repo_paths = await tr_repo.get_active_paths()
    if not repo_paths:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active tracked repositories to scan — reset aborted.",
        )

    ki_repo = KnowledgeItemRepository(db, org_id=org.id)
    features_deleted = await ki_repo.delete_by_category_excluding_source(
        "feature_registry", exclude_source="bud"
    )
    sp_repo = SkillProfileRepository(db, org_id=org.id)
    skills_deleted = await sp_repo.delete_all_for_org()
    synth_repo = SynthesizedFeatureRepository(db, org_id=org.id)
    synth_superseded = await synth_repo.mark_all_superseded()
    repos_reset = await tr_repo.reset_head_shas()
    await db.commit()

    logger.warning(
        "scan_index_reset",
        org_id=str(org.id),
        features_deleted=features_deleted,
        skill_profiles_deleted=skills_deleted,
        synth_features_superseded=synth_superseded,
        repos_reset=repos_reset,
    )

    new_scan_id = uuid.uuid4()
    await _dispatch_scan(
        db,
        background_tasks,
        org_id=org.id,
        scan_id=new_scan_id,
        user=current_user,
        full_rescan=True,
    )
    return ResetIndexResponse(
        new_scan_id=new_scan_id,
        features_deleted=features_deleted,
        skill_profiles_deleted=skills_deleted,
        synth_features_superseded=synth_superseded,
        repos_reset=repos_reset,
    )


# ─── helpers ─────────────────────────────────────────────────────────


async def _assert_parent_scan_exists(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    parent_scan_id: uuid.UUID,
) -> None:
    """Reject resume/retry for a scan the org never owned or that doesn't exist.

    Checkpoints are the authoritative "did this scan exist?" signal —
    they're in Postgres with no TTL. The Redis progress hash ages out
    after 2 h, so a user returning to a day-old failed scan would have
    seen the banner but hit a 404 on Resume if we gated on Redis. We
    therefore key on the checkpoint rows and only use Redis as
    supplemental freshness info (logged, not enforced).

    We intentionally accept scans in *any* status (including completed
    and still-running) as resumable targets — the checkpoint copy is
    idempotent and a still-running scan simply gets a twin; the caller
    sees their child scan_id and can watch it. Preventing overlap is
    the orchestrator's concern, not this API's.
    """
    ck_repo = ScanPhaseCheckpointRepository(db, org_id=org_id)
    rows = await ck_repo.list_for_scan(parent_scan_id)
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Scan {parent_scan_id} has no checkpoints for this org — "
                "either it never ran, belongs to a different org, or "
                "pre-dates checkpoint tracking."
            ),
        )


async def _dispatch_scan(
    db: AsyncSession,
    background_tasks: BackgroundTasks,
    *,
    org_id: uuid.UUID,
    scan_id: uuid.UUID,
    user: User,
    full_rescan: bool = False,
    parent_scan_id: uuid.UUID | None = None,
) -> None:
    """Create progress state and schedule ``run_scan_pipeline``.

    Mirrors the dispatch logic in ``skills.trigger_scan`` so resumes
    see the same preconditions: active tracked repos with mapped
    branches and existing working trees. ``full_rescan`` is only True
    for the ``/scan/reset`` path; resume / retry always pass False.
    ``parent_scan_id`` threads through to ``scans.parent_scan_id`` so
    the lineage column stays accurate for resume-of-resume chains.
    """
    repo_repo = TrackedRepoRepository(db, org_id=org_id)
    repo_paths = await repo_repo.get_active_paths()
    if not repo_paths:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active tracked repositories to scan.",
        )

    await create_scan_progress(
        str(scan_id),
        str(org_id),
        parent_scan_id=str(parent_scan_id) if parent_scan_id else None,
    )
    background_tasks.add_task(
        run_scan_pipeline,
        scan_id=str(scan_id),
        org_id=org_id,
        repo_paths=repo_paths,
        full_rescan=full_rescan,
        user_id=str(user.id),
    )


@router.post(
    "/scan/recover/feature/{synth_feature_id}",
    response_model=FeatureRecoveryResult,
    dependencies=[Depends(require_permissions("org:edit_settings"))],
)
async def recover_merged_feature(
    synth_feature_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FeatureRecoveryResult:
    """Restore a feature that a merge consolidated away.

    Reads the frozen pre-merge row from ``synthesized_features``, then:

    - If the original ``knowledge_item_id`` still exists as an active
      row, links the repo back (idempotent if already linked).
    - Otherwise creates a new ``KnowledgeItem`` from the synth row's
      title / description / capabilities and links it to the repo.

    The synth row itself is left untouched — its ``merge_outcome`` stays
    ``merged_into`` so the audit trail of "this was merged, then a
    human recovered it" remains visible.
    """
    org = await OrganizationRepository(db).get_for_user(current_user)
    synth_repo = SynthesizedFeatureRepository(db, org_id=org.id)
    synth = await synth_repo.get_by_id(synth_feature_id)
    if synth is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Synthesized feature not found: {synth_feature_id}",
        )

    ki_repo = KnowledgeItemRepository(db, org_id=org.id)

    # Prefer reusing the original KI row when it still exists — keeps
    # foreign keys from BUDs / bugs / skill profiles pointing at the
    # same UUID. Only mint a fresh KI when the original was hard-deleted.
    restored_item: KnowledgeItem | None = None
    if synth.knowledge_item_id is not None:
        restored_item = await ki_repo.get_active_by_id(synth.knowledge_item_id)

    created_new = False
    if restored_item is None:
        restored_item = KnowledgeItem(
            org_id=org.id,
            category="feature_registry",
            title=synth.feature_title,
            content=_format_recovered_content(synth.description, synth.capabilities),
            source="scan",
            tags=[],
            is_active=True,
            feature_status="implemented",
        )
        await ki_repo.add(restored_item)
        await ki_repo.flush()
        created_new = True

    await ki_repo.link_to_repo(
        restored_item.id,
        synth.repo_id,
        code_locations=synth.code_locations or None,
    )
    await ki_repo.flush()

    logger.info(
        "feature_recovered_from_synth",
        synth_feature_id=str(synth_feature_id),
        knowledge_item_id=str(restored_item.id),
        repo_id=str(synth.repo_id),
        created_new=created_new,
        previous_merge_outcome=synth.merge_outcome,
    )
    return FeatureRecoveryResult(
        knowledge_item_id=restored_item.id,
        repo_id=synth.repo_id,
        feature_title=synth.feature_title,
        created_new=created_new,
        previous_merge_outcome=synth.merge_outcome,
    )


def _format_recovered_content(
    description: str,
    capabilities: dict[str, list[str]],
) -> str:
    """Rebuild the lean feature-content block from synthesized_features.

    Matches the shape written by ``format_feature_content`` in the MCP
    handler — description first, then a numbered capabilities list.
    Kept as a private helper here instead of importing the MCP formatter
    so the recovery path has no dependency on the MCP layer.
    """
    caps = capabilities.get("capabilities", []) if isinstance(capabilities, dict) else []
    if not caps:
        return description
    numbered = "\n".join(f"{i}. {cap}" for i, cap in enumerate(caps, 1))
    return f"{description}\n\nCapabilities:\n{numbered}"
