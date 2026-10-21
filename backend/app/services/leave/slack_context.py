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
"""What an approver sees under a Slack prompt, so they can decide there.

Leave: the requester's balances and their last leave, from the same
builder as the approvals page, without gender-limited types. WFH: how
many WFH days they'll have with this one (its month and the leave year)
and their last few.
"""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.leave_request import LeaveKind, LeaveRequest
from app.repositories.leave_report import LeaveReportRepository
from app.services.leave.approval_context import requester_context
from app.services.leave.approval_lines import (
    balances_line,
    last_leave_line,
    recent_wfh_line,
    wfh_usage_line,
)
from app.services.leave.calendar_math import leave_year_bounds
from app.services.leave.policies import policy_for_request, today_for
from app.services.leave.wfh_usage import wfh_days_by_month

RECENT_WFH = 3
ZERO = Decimal("0")


async def prompt_context(db: AsyncSession, org_id: uuid.UUID, request: LeaveRequest) -> list[str]:
    """Lines to show under the request; empty for kinds with nothing to add."""
    if request.kind == LeaveKind.LEAVE:
        return await _leave_lines(db, org_id, request)
    if request.kind == LeaveKind.WFH:
        return await _wfh_lines(db, org_id, request)
    return []


async def _leave_lines(db: AsyncSession, org_id: uuid.UUID, request: LeaveRequest) -> list[str]:
    policy = (await policy_for_request(db, org_id, request)).policy
    user = request.user_id
    # The same DM goes to every approver, so gender-limited types (period
    # leave) are never named here: only people who see personal details may
    # see them, in the app (see type_privacy).
    context = await requester_context(db, org_id, {user}, today_for(policy), sees_all=False)
    lines = [
        balances_line(context.balances.get(user, [])),
        last_leave_line(context.last_leave.get(user)),
    ]
    return [line for line in lines if line]


async def _wfh_lines(db: AsyncSession, org_id: uuid.UUID, request: LeaveRequest) -> list[str]:
    policy = (await policy_for_request(db, org_id, request)).policy
    start = request.start_date
    year = leave_year_bounds(start, policy.year_start_month)
    # Approved + pending, so this request is in it. A request crossing the
    # year boundary brings its outside months along; only count the year's.
    by_month = await wfh_days_by_month(db, policy, request.user_id, year.start, year.end)
    month_days = by_month.get((start.year, start.month), ZERO)
    year_days = sum(
        (days for (y, m), days in by_month.items() if year.start <= date(y, m, 1) <= year.end),
        ZERO,
    )
    recent = await LeaveReportRepository(db, org_id=org_id).recent_taken(
        request.user_id, LeaveKind.WFH, today_for(policy), limit=RECENT_WFH
    )
    lines = [wfh_usage_line(start, month_days, year_days), recent_wfh_line(recent)]
    return [line for line in lines if line]
