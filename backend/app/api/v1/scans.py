# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""HTTP endpoints for the multi-repo scan flow.

Mounted under ``/api/v1/reposcanv2`` (URL kept for frontend
compatibility — the ``reposcanv2`` segment is a historical name; all
backend code lives under ``app.services.scan``). Powers the
``/settings/code`` page: list repos, start a scan, poll the timeline,
resume failed runs.
"""

from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db, require_permissions
from app.models.scan_phase import ScanPhase
from app.models.user import User
from app.repositories.organization import OrganizationRepository
from app.repositories.scan import ScanRepository
from app.repositories.scan_run import ScanRunRepository
from app.repositories.tracked_repository import TrackedRepoRepository
from app.schemas.scan import (
    LegacyScanStatusResponse,
    ResumeScanResponse,
    ScanDetailResponse,
    StartScanRequest,
    StartScanResponse,
    TrackedRepoCard,
    V2ConfigResponse,
)
from app.services.scan.runner import (
    ScanAlreadyActiveError,
    cancel_v2_scan,
    resume_v2_scan,
    start_v2_scan,
)
from app.services.scan.serialize import build_legacy_status, build_repo_run_rows
from app.services.scan.synthesis.runner import (
    DEFAULT_MAX_TURNS,
    DEFAULT_MODEL,
    DEFAULT_TIMEOUT_SECONDS,
)

logger = structlog.get_logger(__name__)

# Operator-only because scans hit the filesystem (worktrees + npx).
_REQUIRED_PERMISSION = "org:edit_settings"


router = APIRouter(tags=["scans"])


@router.get("/config", response_model=V2ConfigResponse)
async def get_config() -> V2ConfigResponse:
    """Return the v2 defaults the frontend needs at page load."""
    return V2ConfigResponse(
        default_model=DEFAULT_MODEL,
        default_max_turns=DEFAULT_MAX_TURNS,
        default_timeout_seconds=DEFAULT_TIMEOUT_SECONDS,
        known_phases=[p.value for p in ScanPhase],
    )


@router.get(
    "/repos",
    response_model=list[TrackedRepoCard],
    dependencies=[Depends(require_permissions(_REQUIRED_PERMISSION))],
)
async def list_repos(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[TrackedRepoCard]:
    """Tracked repos for the v2 scan-page selection grid."""
    org_id = await _resolve_org_id(current_user, db)
    rows = await TrackedRepoRepository(db, org_id=org_id).list_all_ordered_by_name()
    # One join across all repos: for each repo, attach its most-recent
    # ScanRepoRun so the row can render "last scan: 2 hours ago • 17
    # features • done" without any further round trips.
    latest_runs = await ScanRunRepository(db, org_id=org_id).find_latest_per_repo(
        repo_ids=[row.id for row in rows]
    )
    cards: list[TrackedRepoCard] = []
    for row in rows:
        last_run = latest_runs.get(row.id)
        cards.append(
            TrackedRepoCard(
                id=row.id,
                name=row.name,
                path=row.path,
                status=row.status,
                head_sha=row.head_sha,
                last_scanned_at=row.last_scanned_at.isoformat() if row.last_scanned_at else None,
                feature_count=row.feature_count,
                last_scan_status=last_run.status if last_run is not None else None,
                last_scan_finished_at=(
                    last_run.finished_at.isoformat()
                    if last_run is not None and last_run.finished_at is not None
                    else None
                ),
                last_scan_started_at=(
                    last_run.started_at.isoformat()
                    if last_run is not None and last_run.started_at is not None
                    else None
                ),
                last_scan_feature_count=(last_run.feature_count if last_run is not None else None),
                last_scan_id=last_run.scan_id if last_run is not None else None,
            )
        )
    return cards


@router.post(
    "/scans",
    response_model=StartScanResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_permissions(_REQUIRED_PERMISSION))],
)
async def create_scan(
    body: StartScanRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StartScanResponse:
    """Queue a v2 scan across the selected repositories."""
    if not body.repo_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="repo_ids must be non-empty",
        )
    org_id = await _resolve_org_id(current_user, db)
    try:
        scan_id = await start_v2_scan(org_id=org_id, repo_ids=body.repo_ids, config=body.config)
    except ScanAlreadyActiveError as exc:
        # 409 carries the in-flight scan_id so the frontend can switch
        # the timeline view to it instead of starting a duplicate.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "scan_already_active",
                "scan_id": str(exc.scan_id),
                "status": exc.status,
                "message": "A scan is already running for this org.",
            },
        ) from exc
    logger.info(
        "scan_create",
        org_id=str(org_id),
        scan_id=str(scan_id),
        repo_count=len(body.repo_ids),
    )
    return StartScanResponse(scan_id=scan_id, status="queued", repo_count=len(body.repo_ids))


@router.post(
    "/scans/{scan_id}/resume",
    response_model=ResumeScanResponse,
    dependencies=[Depends(require_permissions(_REQUIRED_PERMISSION))],
)
async def resume_scan(
    scan_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ResumeScanResponse:
    """Re-queue any non-DONE repo runs in this scan."""
    org_id = await _resolve_org_id(current_user, db)
    try:
        requeued = await resume_v2_scan(org_id=org_id, scan_id=scan_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    logger.info(
        "scan_resume",
        org_id=str(org_id),
        scan_id=str(scan_id),
        requeued=requeued,
    )
    return ResumeScanResponse(scan_id=scan_id, requeued=requeued)


@router.post(
    "/scans/{scan_id}/cancel",
    dependencies=[Depends(require_permissions(_REQUIRED_PERMISSION))],
)
async def cancel_scan(
    scan_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Cancel an in-flight scan: stop the task and flip the subtree to FAILED."""
    org_id = await _resolve_org_id(current_user, db)
    found = await cancel_v2_scan(org_id=org_id, scan_id=scan_id)
    if not found:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scan {scan_id} not found",
        )
    logger.info("scan_cancel", org_id=str(org_id), scan_id=str(scan_id))
    return {"status": "cancelled", "scan_id": str(scan_id)}


@router.get(
    "/scans/{scan_id}/status",
    response_model=LegacyScanStatusResponse,
    response_model_by_alias=True,
)
async def get_scan_status(
    scan_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LegacyScanStatusResponse:
    """Legacy ScanStatusData shape — used by SetupChecklist polling.

    The new pipeline records progress in ``scan_repo_runs`` /
    ``scan_repo_steps``; this endpoint reshapes that data back into the
    flat fields the existing frontend components expect.
    """
    org_id = await _resolve_org_id(current_user, db)
    scan = await ScanRepository(db, org_id=org_id).get(scan_id)
    if scan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scan {scan_id} not found",
        )
    return await build_legacy_status(db, org_id=org_id, scan=scan)


@router.get(
    "/scans/latest",
    response_model=ScanDetailResponse,
    dependencies=[Depends(require_permissions(_REQUIRED_PERMISSION))],
)
async def get_latest_scan(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ScanDetailResponse:
    """Most recent scan for this org. 404 when the org has never scanned.

    Used by the settings page to rehydrate the timeline + per-row chips
    when localStorage is empty (different browser, cleared storage, or
    a session that pre-dates the persisted-id mechanism).
    """
    # Route is declared BEFORE `/scans/{scan_id}` so "latest" is matched
    # as a literal path segment instead of being parsed as a UUID.
    org_id = await _resolve_org_id(current_user, db)
    scan = await ScanRepository(db, org_id=org_id).get_latest()
    if scan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    repo_runs = await build_repo_run_rows(db, org_id=org_id, scan_id=scan.id)
    return ScanDetailResponse(
        scan_id=scan.id,
        status=scan.status,
        started_at=scan.created_at.isoformat(),
        repo_runs=repo_runs,
    )


@router.get(
    "/scans/{scan_id}",
    response_model=ScanDetailResponse,
    dependencies=[Depends(require_permissions(_REQUIRED_PERMISSION))],
)
async def get_scan(
    scan_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ScanDetailResponse:
    """Timeline payload — scan status + every repo run + every step."""
    org_id = await _resolve_org_id(current_user, db)
    scan = await ScanRepository(db, org_id=org_id).get(scan_id)
    if scan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    repo_runs = await build_repo_run_rows(db, org_id=org_id, scan_id=scan_id)
    return ScanDetailResponse(
        scan_id=scan.id,
        status=scan.status,
        started_at=scan.created_at.isoformat(),
        repo_runs=repo_runs,
    )


# --- helpers ------------------------------------------------------


async def _resolve_org_id(user: User, db: AsyncSession) -> uuid.UUID:
    """Pick the user's primary org. Mirrors the sandbox endpoints' logic."""
    org = await OrganizationRepository(db).get_for_user(user)
    if org is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is not a member of any organisation",
        )
    return org.id
