# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""BUD estimation API endpoints.

Provides endpoints for viewing, recalculating, and overriding per-phase
delivery estimates with AI-PERT + Monte Carlo confidence intervals.
"""

from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db, require_permissions
from app.models.bud import BUDDocument
from app.models.user import User
from app.repositories.bud import BUDRepository
from app.repositories.bud_estimate import BUDEstimateSnapshotRepository
from app.repositories.organization import OrganizationRepository
from app.schemas.bud import (
    BUDEstimatesRead,
    EstimateOverrideRequest,
    EstimateSnapshotRead,
    PhaseEstimate,
)
from app.services.org_settings import get_phase_order

logger = structlog.get_logger(__name__)

router = APIRouter()


@router.get(
    "/estimates",
    response_model=BUDEstimatesRead,
    dependencies=[Depends(require_permissions("buds:view"))],
)
async def get_estimates(
    bud_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BUDEstimatesRead:
    """Get current estimates for all phases of a BUD."""
    bud = await _get_bud_or_404(bud_id, current_user.org_id, db)
    return _build_estimates_response(bud)


@router.post(
    "/estimates/recalculate",
    response_model=BUDEstimatesRead,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_permissions("buds:edit"))],
)
async def recalculate_estimates(
    bud_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BUDEstimatesRead:
    """Force recalculation of all phase estimates."""
    from app.services.bud_estimation import estimate_bud_dates

    bud = await _get_bud_or_404(bud_id, current_user.org_id, db)
    await estimate_bud_dates(
        db,
        current_user.org_id,
        bud,
        trigger="manual",
        actor_id=current_user.id,
        actor_name=current_user.name,
    )
    await db.refresh(bud)
    return _build_estimates_response(bud)


@router.patch(
    "/estimates/{phase}",
    response_model=PhaseEstimate,
    dependencies=[Depends(require_permissions("buds:edit"))],
)
async def override_estimate(
    bud_id: uuid.UUID,
    phase: str,
    body: EstimateOverrideRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PhaseEstimate:
    """Override a single phase's estimated date. Requires reason.

    Validates ``phase`` against the org's active phase list so a UAT-disabled
    org rejects ``phase="uat"`` here at the HTTP boundary with a clean 400 —
    without this, the in-service backstop in ``override_phase_date`` would
    still catch it but as an uncaught ``ValueError`` surfaced as HTTP 500.
    """
    org = await OrganizationRepository(db).get_by_id(current_user.org_id)
    allowed_phases = get_phase_order(org.config if org else None)
    if phase not in allowed_phases:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid phase '{phase}' for this org (allowed: {allowed_phases})",
        )

    from app.services.bud_estimation import override_phase_date

    bud = await _get_bud_or_404(bud_id, current_user.org_id, db)
    result = await override_phase_date(
        db,
        current_user.org_id,
        bud,
        phase,
        body.estimated_completion,
        body.reason,
        current_user.id,
        current_user.name,
    )

    return PhaseEstimate(
        phase=phase,
        estimated_completion=result["estimated_completion"],
        p50_date=result.get("p50_date"),
        p70_date=result.get("p70_date"),
        p85_date=result.get("p85_date"),
        source=result["source"],
        confidence=result["confidence"],
        override_reason=result.get("override_reason"),
    )


@router.get(
    "/estimates/history",
    response_model=list[EstimateSnapshotRead],
    dependencies=[Depends(require_permissions("buds:view"))],
)
async def get_estimate_history(
    bud_id: uuid.UUID,
    limit: int = Query(default=20, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[EstimateSnapshotRead]:
    """Get historical estimate snapshots for a BUD."""
    await _get_bud_or_404(bud_id, current_user.org_id, db)
    repo = BUDEstimateSnapshotRepository(db, org_id=current_user.org_id)
    return await repo.list_for_bud(bud_id, limit=limit)


# ── Helpers ──────────────────────────────────────────────────────


async def _get_bud_or_404(
    bud_id: uuid.UUID,
    org_id: uuid.UUID,
    db: AsyncSession,
) -> BUDDocument:
    """Fetch a BUD by ID or raise 404."""
    bud_repo = BUDRepository(db, org_id=org_id)
    bud = await bud_repo.get_by_id(bud_id)
    if bud is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="BUD not found",
        )
    return bud


def _build_estimates_response(bud: BUDDocument) -> BUDEstimatesRead:
    """Build BUDEstimatesRead from a BUD's estimated_dates JSONB.

    Iterates whatever phase rows are actually present in ``estimated_dates``
    (which ``estimate_bud_dates`` already filtered by the org's phase order)
    rather than walking a fixed list — so UAT-disabled orgs naturally return
    no UAT row without this function needing to know about the toggle.
    """
    est = bud.estimated_dates or {}
    summary = est.get("_summary", {})

    phases = []
    for phase, phase_data in est.items():
        # Skip the "_summary" metadata key and any non-dict values.
        if phase.startswith("_") or not isinstance(phase_data, dict):
            continue
        if "estimated_completion" not in phase_data:
            continue
        phases.append(
            PhaseEstimate(
                phase=phase,
                estimated_completion=phase_data["estimated_completion"],
                p50_date=phase_data.get("p50_date"),
                p70_date=phase_data.get("p70_date"),
                p85_date=phase_data.get("p85_date"),
                expected_days=phase_data.get("expected_days"),
                std_dev_days=phase_data.get("std_dev_days"),
                source=phase_data.get("source", "ai_pert"),
                confidence=phase_data.get("confidence", 0.5),
                override_reason=phase_data.get("override_reason"),
            )
        )

    return BUDEstimatesRead(
        bud_id=bud.id,
        complexity=bud.complexity,
        phases=phases,
        prod_p50=summary.get("prod_p50"),
        prod_p70=summary.get("prod_p70"),
        prod_p85=summary.get("prod_p85"),
        generated_at=summary.get("generated_at"),
        trigger=summary.get("trigger"),
    )
