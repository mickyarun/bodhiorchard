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
"""How much WFH a member has used, and whether a new request is auto-approved."""

import uuid
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.leave_policy import LeavePolicy
from app.models.leave_request import HalfDay, LeaveKind
from app.repositories.leave_request import LeaveRequestRepository
from app.services.leave.calendar_math import days_by_month
from app.services.leave.policies import mandatory_holidays
from app.services.leave.wfh_policy import Month, needs_approval

ZERO = Decimal("0")


def _month_span(start: date, end: date) -> tuple[date, date]:
    first = start.replace(day=1)
    last = (end.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    return first, last


async def wfh_days_by_month(
    db: AsyncSession, policy: LeavePolicy, user_id: uuid.UUID, start: date, end: date
) -> dict[Month, Decimal]:
    """Approved + pending WFH working days per month across the months of a range."""
    first, last = _month_span(start, end)
    holidays = await mandatory_holidays(db, policy, first, last)
    requests = await LeaveRequestRepository(db, org_id=policy.org_id).active_between(
        [user_id], first, last, kinds=[LeaveKind.WFH]
    )
    used: dict[Month, Decimal] = {}
    for req in requests:
        for month, days in days_by_month(
            req.start_date,
            req.end_date,
            req.half_day,
            working_days=policy.working_days,
            holidays=holidays,
        ).items():
            used[month] = used.get(month, ZERO) + days
    return used


async def wfh_auto_approved(
    db: AsyncSession,
    policy: LeavePolicy,
    user_id: uuid.UUID,
    start: date,
    end: date,
    half_day: HalfDay,
) -> bool:
    """True if the policy approves this WFH request without a manager."""
    first, last = _month_span(start, end)
    holidays = await mandatory_holidays(db, policy, first, last)
    requested = days_by_month(
        start, end, half_day, working_days=policy.working_days, holidays=holidays
    )
    already = await wfh_days_by_month(db, policy, user_id, start, end)
    return not needs_approval(
        policy.wfh_approval, policy.wfh_monthly_auto_days, already=already, requested=requested
    )
