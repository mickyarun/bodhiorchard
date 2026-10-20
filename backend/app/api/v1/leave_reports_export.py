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

"""The leave reports as CSV downloads (same access and filters as the JSON)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1._csv import csv_response
from app.api.v1.leave_reports import viewer_scope
from app.core.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.leave_report_filters import BalanceFilters, RegisterFilters, SummaryFilters
from app.services.leave.errors import LeaveInvalidError
from app.services.leave.report_scope import ReportScope
from app.services.leave.reports.balances import balance_report
from app.services.leave.reports.csv_export import csv_filename, to_csv
from app.services.leave.reports.csv_rows import balance_rows, register_rows, summary_rows
from app.services.leave.reports.register import register_report
from app.services.leave.reports.summary import summary_report

router = APIRouter(tags=["leave-reports"])

TOO_MANY = "Too many requests to export at once. Narrow the dates or filters."


@router.get("/reports/summary.csv", response_class=Response)
async def export_summary(
    filters: Annotated[SummaryFilters, Query()],
    current_user: User = Depends(get_current_user),
    scope: ReportScope = Depends(viewer_scope),
    db: AsyncSession = Depends(get_db),
) -> Response:
    report = await summary_report(db, current_user.org_id, scope, filters)
    header, rows = summary_rows(report)
    name = csv_filename("summary", filters.start, filters.end)
    return csv_response(to_csv(header, rows), name)


@router.get("/reports/register.csv", response_class=Response)
async def export_register(
    filters: Annotated[RegisterFilters, Query()],
    current_user: User = Depends(get_current_user),
    scope: ReportScope = Depends(viewer_scope),
    db: AsyncSession = Depends(get_db),
) -> Response:
    report = await register_report(db, current_user.org_id, scope, filters)
    if report.truncated:
        raise LeaveInvalidError(TOO_MANY)
    header, rows = register_rows(report.rows)
    name = csv_filename("requests", filters.start, filters.end)
    return csv_response(to_csv(header, rows), name)


@router.get("/reports/balances.csv", response_class=Response)
async def export_balances(
    filters: Annotated[BalanceFilters, Query()],
    current_user: User = Depends(get_current_user),
    scope: ReportScope = Depends(viewer_scope),
    db: AsyncSession = Depends(get_db),
) -> Response:
    report = await balance_report(db, current_user.org_id, scope, filters)
    header, rows = balance_rows(report)
    years = sorted({r.leave_year for r in report.rows})
    return csv_response(to_csv(header, rows), csv_filename("balances", *years))
