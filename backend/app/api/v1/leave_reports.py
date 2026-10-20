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

"""Leave reports for HR, the owner (leave:reports) and managers (direct reports)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import PermissionSet, get_current_user, get_db, get_permission_set
from app.models.user import User
from app.schemas.leave_report_filters import BalanceFilters, RegisterFilters, SummaryFilters
from app.schemas.leave_reports import (
    BalanceReport,
    RegisterReport,
    ReportScopeRead,
    SummaryReport,
)
from app.services.leave.report_scope import ReportScope, report_scope
from app.services.leave.reports.balances import balance_report
from app.services.leave.reports.register import register_report
from app.services.leave.reports.scope_options import scope_options
from app.services.leave.reports.summary import summary_report

router = APIRouter(tags=["leave-reports"])


async def viewer_scope(
    current_user: User = Depends(get_current_user),
    perms: PermissionSet = Depends(get_permission_set),
    db: AsyncSession = Depends(get_db),
) -> ReportScope:
    """Everyone for leave:reports, else the viewer's direct reports (403 if none)."""
    return await report_scope(db, current_user, perms)


@router.get("/reports/scope", response_model=ReportScopeRead)
async def get_report_scope(
    current_user: User = Depends(get_current_user),
    scope: ReportScope = Depends(viewer_scope),
    db: AsyncSession = Depends(get_db),
) -> ReportScopeRead:
    """Who and what the viewer can report on, for the filter pickers."""
    return await scope_options(db, current_user.org_id, scope)


@router.get("/reports/summary", response_model=SummaryReport)
async def get_summary(
    filters: Annotated[SummaryFilters, Query()],
    current_user: User = Depends(get_current_user),
    scope: ReportScope = Depends(viewer_scope),
    db: AsyncSession = Depends(get_db),
) -> SummaryReport:
    """Employee-wise leave taken in the range."""
    return await summary_report(db, current_user.org_id, scope, filters)


@router.get("/reports/register", response_model=RegisterReport)
async def get_register(
    filters: Annotated[RegisterFilters, Query()],
    current_user: User = Depends(get_current_user),
    scope: ReportScope = Depends(viewer_scope),
    db: AsyncSession = Depends(get_db),
) -> RegisterReport:
    """Every request overlapping the range."""
    return await register_report(db, current_user.org_id, scope, filters)


@router.get("/reports/balances", response_model=BalanceReport)
async def get_balances(
    filters: Annotated[BalanceFilters, Query()],
    current_user: User = Depends(get_current_user),
    scope: ReportScope = Depends(viewer_scope),
    db: AsyncSession = Depends(get_db),
) -> BalanceReport:
    """Balances per member and leave type for a leave year."""
    return await balance_report(db, current_user.org_id, scope, filters)
