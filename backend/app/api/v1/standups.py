"""Standup report API endpoints."""

from datetime import date

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.standup import StandupReportListItem, StandupReportRead
from app.services.standup_service import (
    get_or_generate_today,
    get_report_by_date,
    list_recent,
    report_to_read,
)

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["standups"])


@router.get("/today", response_model=StandupReportRead)
async def get_standup_today(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StandupReportRead:
    """Return today's standup, generating it on-demand if needed."""
    try:
        report = await get_or_generate_today(db, current_user.org_id)
    except Exception:
        logger.exception(
            "standup_generation_failed",
            org_id=str(current_user.org_id),
        )
        raise HTTPException(500, "Failed to generate standup report") from None
    return report_to_read(report)


@router.get("/list", response_model=list[StandupReportListItem])
async def list_standups(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[StandupReportListItem]:
    """Return the last 14 standup reports."""
    reports = await list_recent(db, current_user.org_id, limit=14)
    items: list[StandupReportListItem] = []
    for r in reports:
        content = r.content or {}
        flags_data = r.flags or {}
        items.append(
            StandupReportListItem(
                id=str(r.id),
                date=r.date,
                member_count=len(content.get("members", [])),
                flag_count=len(flags_data.get("flags", [])),
                created_at=r.created_at,
            )
        )
    return items


@router.get("/{target_date}", response_model=StandupReportRead)
async def get_standup_by_date(
    target_date: date,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StandupReportRead:
    """Return a standup report for a specific date."""
    report = await get_report_by_date(db, current_user.org_id, target_date)
    if not report:
        raise HTTPException(status_code=404, detail=f"No standup for {target_date}")
    return report_to_read(report)
