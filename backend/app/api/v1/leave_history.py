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

"""A member's leave history: for them, their managers, HR and leave:reports."""

import uuid

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1._csv import csv_response
from app.core.deps import PermissionSet, get_current_user, get_db, get_permission_set
from app.models.leave_request import LeaveKind, LeaveStatus
from app.models.user import User
from app.schemas.leave_reports import RegisterReport
from app.services.leave.errors import LeaveForbiddenError
from app.services.leave.member_balances import require_member
from app.services.leave.report_scope import may_view_member_leave
from app.services.leave.reports.csv_export import csv_filename, to_csv
from app.services.leave.reports.csv_rows import register_rows
from app.services.leave.reports.register import member_history
from app.services.leave.type_privacy import sees_restricted

router = APIRouter(tags=["leave"])


async def _history(
    db: AsyncSession,
    viewer: User,
    perms: PermissionSet,
    user_id: uuid.UUID,
    year: int | None,
    kind: LeaveKind | None,
    status: LeaveStatus | None,
) -> RegisterReport:
    """404 for strangers, 403 unless the viewer may see this member's leave."""
    await require_member(db, viewer.org_id, user_id)
    if not await may_view_member_leave(db, viewer, perms, user_id):
        raise LeaveForbiddenError("You can't see this person's leave.")
    return await member_history(
        db,
        viewer.org_id,
        user_id,
        year,
        sees_restricted=sees_restricted(perms) or viewer.id == user_id,
        kind=kind,
        status=status,
    )


@router.get("/history/{user_id}", response_model=RegisterReport)
async def get_history(
    user_id: uuid.UUID,
    year: int | None = Query(None, ge=2000, le=2100),
    kind: LeaveKind | None = None,
    status: LeaveStatus | None = None,
    current_user: User = Depends(get_current_user),
    perms: PermissionSet = Depends(get_permission_set),
    db: AsyncSession = Depends(get_db),
) -> RegisterReport:
    """The member's requests in a leave year (the current one by default)."""
    return await _history(db, current_user, perms, user_id, year, kind, status)


@router.get("/history/{user_id}/export", response_class=Response)
async def export_history(
    user_id: uuid.UUID,
    year: int | None = Query(None, ge=2000, le=2100),
    kind: LeaveKind | None = None,
    status: LeaveStatus | None = None,
    current_user: User = Depends(get_current_user),
    perms: PermissionSet = Depends(get_permission_set),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """The same as CSV; the file is named by year, never by person."""
    report = await _history(db, current_user, perms, user_id, year, kind, status)
    header, rows = register_rows(report.rows)
    years = sorted({r.start_date.year for r in report.rows}) or ([year] if year else [])
    return csv_response(to_csv(header, rows), csv_filename("history", *years))
