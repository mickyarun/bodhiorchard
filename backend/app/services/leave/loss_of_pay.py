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
change). Re-pricing uses the balance without this request, so when a
request shrinks its loss-of-pay days go first. When the
balance moves under leave already booked (an adjustment either way, a
cancelled or rejected request, a recalculated allocation), the member's
leave of that type is re-priced together, so the balance never ends up
below zero: whatever it can't cover is loss of pay, and the earliest
leave is paid first.
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


async def reprice(db: AsyncSession, member: MemberPolicy, request: LeaveRequest) -> None:
    """Re-split an open leave request into paid and loss-of-pay days.

    Callers hold the member's lock and have already set ``request.days``.
    It is priced against the balance without its own paid days, so for
    the balance query it is all loss of pay until it is split.
    """
    if request.leave_type_id is None:
        return
    had = min(request.lop_days, request.days)
    request.lop_days = request.days
    await db.flush()
    policy = member.policy
    year = leave_year_bounds(request.start_date, policy.year_start_month)
    lines = await balances_for(
        db,
        policy=policy,
        profile=member.profile,
        user_id=request.user_id,
        year=year,
        on=request.start_date,
        persist_type_id=request.leave_type_id,
    )
    line = find_line(lines, request.leave_type_id)
    if line is None:
        # The type was switched off: there's no balance to price against,
        # so keep the loss of pay it already had (no more than its days).
        request.lop_days = had
    elif line.available is None:
        request.lop_days = ZERO
    else:
        _paid, request.lop_days = split_paid(request.days, line.available)
    await db.flush()


async def rebalance(
    db: AsyncSession, member: MemberPolicy, user_id: uuid.UUID, leave_type_id: uuid.UUID, on: date
) -> None:
    """Re-price a member's leave of one type after its balance moved, either way.

    ``on`` is any day in the leave year that changed (counted on
    ``member``'s policy). Every approved and pending request of the type in
    that year is released and priced again in date order, so paid days go
    to the earliest leave: days freed up reach the oldest loss of pay, and
    days taken away turn the latest leave unpaid first. Nothing is touched
    while the balance covers everything booked. Callers hold the member's lock.
    """
    policy = member.policy
    year = leave_year_bounds(on, policy.year_start_month)
    lines = await balances_for(
        db, policy=policy, profile=member.profile, user_id=user_id, year=year, on=year.start
    )
    line = find_line(lines, leave_type_id)
    if line is None or line.available is None:
        # Switched off or no limit: there's no balance to price against.
        return
    requests = await LeaveUsageRepository(db, org_id=policy.org_id).active_in_year(
        user_id, leave_type_id, year.start, year.end
    )
    if line.short == ZERO and not any(r.lop_days > ZERO for r in requests):
        return
    for request in requests:
        request.lop_days = request.days
    for request in requests:
        await reprice(db, await policy_for_request(db, policy.org_id, request), request)
