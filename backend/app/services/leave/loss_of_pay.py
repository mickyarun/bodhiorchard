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

"""Loss of pay: the days of a leave request the balance doesn't cover.

Nobody is stopped from taking leave because their balance ran out. The
days the balance covers are paid; the rest are loss of pay. Only paid
days count against the balance.

A request is re-priced whenever its days or the balance behind it may
have moved (approval, cancelling the rest of a leave under way, a holiday
change). Re-pricing uses the balance without this request's own paid
days, so when a request shrinks its loss-of-pay days go first. When
balance frees up (an adjustment, a cancelled or rejected request), the
member's leave that still has loss of pay is re-priced, oldest first.
"""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.leave_request import LeaveRequest
from app.repositories.leave_usage import LeaveUsageRepository
from app.services.leave.balances import balances_for, find_line
from app.services.leave.calendar_math import leave_year_bounds
from app.services.leave.policies import MemberPolicy, policy_for_request

ZERO = Decimal("0")


def split_paid(days: Decimal, available: Decimal | None) -> tuple[Decimal, Decimal]:
    """``(paid, loss_of_pay)`` for ``days`` against ``available`` (None = no limit)."""
    if available is None:
        return days, ZERO
    paid = min(days, max(available, ZERO))
    return paid, days - paid


def paid_days(request: LeaveRequest) -> Decimal:
    """Days of ``request`` that come out of the balance."""
    return request.days - request.lop_days


async def reprice(db: AsyncSession, member: MemberPolicy, request: LeaveRequest) -> None:
    """Re-split an open leave request into paid and loss-of-pay days.

    Callers hold the member's lock and have already set ``request.days``.
    The request still counts in the balance, so its own paid days are
    added back before splitting.
    """
    if request.leave_type_id is None:
        return
    # Fewer days than loss of pay: give the extra back before the database
    # sees it. Then let the balance query see this request as it is now.
    request.lop_days = min(request.lop_days, request.days)
    await db.flush()
    policy = member.policy
    year = leave_year_bounds(request.start_date, policy.year_start_month)
    lines = await balances_for(
        db,
        policy=policy,
        profile=member.profile,
        user_id=request.user_id,
        year=year,
        persist_type_id=request.leave_type_id,
    )
    line = find_line(lines, request.leave_type_id)
    if line is None:
        # The type was switched off: there's no balance to price against,
        # so keep the loss of pay it already had.
        pass
    elif line.available is None:
        request.lop_days = ZERO
    else:
        available = line.available + paid_days(request)
        _paid, request.lop_days = split_paid(request.days, available)
    await db.flush()


async def give_back(
    db: AsyncSession, member: MemberPolicy, user_id: uuid.UUID, leave_type_id: uuid.UUID, on: date
) -> None:
    """Re-price a member's leave with loss of pay after balance freed up.

    ``on`` is any day in the leave year that changed (counted on
    ``member``'s policy). Callers hold the member's lock.
    """
    year = leave_year_bounds(on, member.policy.year_start_month)
    requests = await LeaveUsageRepository(db, org_id=member.policy.org_id).open_with_lop(
        user_id, leave_type_id, year.start, year.end
    )
    for request in requests:
        await reprice(db, await policy_for_request(db, member.policy.org_id, request), request)
