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

"""Working days per calendar month: already booked, and in a new request.

Feeds the monthly checks in :mod:`app.services.leave.monthly_limit`.
"""

import uuid
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.leave_policy import LeavePolicy
from app.models.leave_request import HalfDay, LeaveKind
from app.repositories.leave_request import LeaveRequestRepository
from app.services.leave.calendar_math import days_by_month
from app.services.leave.monthly_limit import Month
from app.services.leave.policies import mandatory_holidays

ZERO = Decimal("0")


def month_span(start: date, end: date) -> tuple[date, date]:
    """The first day of ``start``'s month to the last day of ``end``'s."""
    first = start.replace(day=1)
    last = (end.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    return first, last


async def booked_by_month(
    db: AsyncSession,
    policy: LeavePolicy,
    user_id: uuid.UUID,
    start: date,
    end: date,
    *,
    kind: LeaveKind,
    leave_type_id: uuid.UUID | None = None,
) -> dict[Month, Decimal]:
    """Approved + pending working days of ``kind`` (and type) per month of the range."""
    first, last = month_span(start, end)
    holidays = await mandatory_holidays(db, policy, first, last)
    requests = await LeaveRequestRepository(db, org_id=policy.org_id).active_between(
        [user_id], first, last, kinds=[kind]
    )
    used: dict[Month, Decimal] = {}
    for req in requests:
        if leave_type_id is not None and req.leave_type_id != leave_type_id:
            continue
        for month, days in days_by_month(
            req.start_date,
            req.end_date,
            req.half_day,
            working_days=policy.working_days,
            holidays=holidays,
        ).items():
            used[month] = used.get(month, ZERO) + days
    return used


async def requested_by_month(
    db: AsyncSession, policy: LeavePolicy, start: date, end: date, half_day: HalfDay
) -> dict[Month, Decimal]:
    """A new request's working days per month."""
    holidays = await mandatory_holidays(db, policy, *month_span(start, end))
    return days_by_month(start, end, half_day, working_days=policy.working_days, holidays=holidays)
