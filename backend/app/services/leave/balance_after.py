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

"""Balance-after for many pending requests at once (the approvals queue).

Read-only: an allocation not yet in the ledger is worked out the same way
:func:`app.services.leave.balances.balances_for` would, but never written.
Each request is priced on the policy it was made under, which is also the
policy approval re-checks it against.
"""

import uuid
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.leave_request import LeaveKind, LeaveRequest
from app.repositories.employee_profile import EmployeeProfileRepository
from app.repositories.leave_ledger import LeaveLedgerRepository
from app.repositories.leave_policy import LeavePolicyRepository
from app.repositories.leave_type import LeaveTypeRepository
from app.repositories.leave_usage import LeaveUsageRepository
from app.services.leave.accrual import earned_by
from app.services.leave.allocation import allocation_for_year
from app.services.leave.balances import proration_rule
from app.services.leave.calendar_math import LeaveYearBounds, leave_year_bounds
from app.services.leave.policies import effective_from

ZERO = Decimal("0")
UsageKey = tuple[uuid.UUID, uuid.UUID, int]


@dataclass(frozen=True)
class AfterApproval:
    """Days left once approved (None: no limit), in the request's own leave year."""

    days: Decimal | None
    year: int


async def balances_after(
    db: AsyncSession, org_id: uuid.UUID, requests: Sequence[LeaveRequest]
) -> dict[uuid.UUID, AfterApproval]:
    """``{request_id: days left once approved}`` for priced leave requests.

    WFH, optional holidays and requests whose type or policy is gone are
    left out; an unlimited type gets ``days=None``.

    Pending days already count against the balance, so this is simply the
    available balance for the request's type and leave year.
    """
    priced = [r for r in requests if r.kind == LeaveKind.LEAVE and r.leave_type_id is not None]
    out: dict[uuid.UUID, AfterApproval] = {}
    if not priced:
        return out
    users = {r.user_id for r in priced}
    type_ids = {r.leave_type_id for r in priced if r.leave_type_id is not None}
    policies = await LeavePolicyRepository(db, org_id=org_id).by_ids({r.policy_id for r in priced})
    types = await LeaveTypeRepository(db, org_id=org_id).by_ids(type_ids)
    profiles = await EmployeeProfileRepository(db, org_id=org_id).by_users(users)
    ledger = await LeaveLedgerRepository(db, org_id=org_id).type_totals(users, type_ids)
    years = {
        r.id: leave_year_bounds(r.start_date, policies[r.policy_id].year_start_month)
        for r in priced
        if r.policy_id in policies
    }
    if not years:
        return out
    usage = await _usage(db, org_id, priced, years)
    for request in priced:
        leave_type = types.get(request.leave_type_id) if request.leave_type_id else None
        year = years.get(request.id)
        if leave_type is None or year is None:
            continue
        if leave_type.annual_quota_days is None:
            out[request.id] = AfterApproval(days=None, year=year.label)
            continue
        key = (request.user_id, leave_type.id, year.label)
        allocated, adjustments = ledger.get(key, (None, ZERO))
        joined = effective_from(profiles.get(request.user_id))
        if allocated is None:
            allocated = allocation_for_year(
                leave_type.annual_quota_days,
                joined,
                year.start,
                year.end,
                proration_rule(policies[request.policy_id]),
            )
        # As the request was priced: what is earned by the day it starts.
        earned = earned_by(
            allocated, leave_type.accrual, joined, year.start, year.end, request.start_date
        )
        out[request.id] = AfterApproval(
            days=earned + adjustments - usage.get(key, ZERO), year=year.label
        )
    return out


async def _usage(
    db: AsyncSession,
    org_id: uuid.UUID,
    priced: Sequence[LeaveRequest],
    years: dict[uuid.UUID, LeaveYearBounds],
) -> dict[UsageKey, Decimal]:
    """Approved plus pending days per (member, type, leave year) in one query."""
    # The leave years each (member, type) is being priced for.
    wanted: dict[tuple[uuid.UUID, uuid.UUID], set[LeaveYearBounds]] = defaultdict(set)
    for request in priced:
        if request.id in years and request.leave_type_id is not None:
            wanted[(request.user_id, request.leave_type_id)].add(years[request.id])
    bounds = list(years.values())
    rows = await LeaveUsageRepository(db, org_id=org_id).leave_days_by_start(
        {r.user_id for r in priced},
        {r.leave_type_id for r in priced if r.leave_type_id is not None},
        min(b.start for b in bounds),
        max(b.end for b in bounds),
    )
    totals: dict[UsageKey, Decimal] = defaultdict(lambda: ZERO)
    for user_id, type_id, _status, start, days in rows:
        for year in wanted.get((user_id, type_id), ()):
            if year.start <= start <= year.end:
                totals[(user_id, type_id, year.label)] += days
    return totals
