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

"""Balance lines for many people at once, in a fixed number of queries.

The balances report, the summary's "left" figures and the approvals queue
all read balances through here, built by the same :func:`build_line` the
Leave page uses, so the numbers agree everywhere. Read-only: an allocation
not yet in the ledger is worked out, never written.
"""

import uuid
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.leave_policy import LeavePolicy
from app.repositories.leave_ledger import LeaveLedgerRepository
from app.repositories.leave_type import LeaveTypeRepository
from app.repositories.leave_usage import LeaveUsageRepository
from app.services.leave.accrual import Booking
from app.services.leave.balances import (
    BalanceLine,
    booking,
    build_line,
    day_in_year,
    proration_rule,
)
from app.services.leave.calendar_math import (
    LeaveYearBounds,
    leave_year_bounds,
    leave_year_by_label,
)
from app.services.leave.eligibility import usable_types
from app.services.leave.policies import today_for
from app.services.leave.reports.population import Person

ZERO = Decimal("0")
YearFor = Callable[[LeavePolicy], LeaveYearBounds]


def leave_year_for(label: int | None) -> YearFor:
    """The policy's leave year labelled ``label``, or its current one."""

    def pick(policy: LeavePolicy) -> LeaveYearBounds:
        if label is not None:
            return leave_year_by_label(label, policy.year_start_month)
        return leave_year_bounds(today_for(policy), policy.year_start_month)

    return pick


@dataclass(frozen=True)
class PersonBalances:
    """One member's active leave types for one leave year, plus loss of pay in it."""

    year: LeaveYearBounds
    lines: list[BalanceLine]
    lop_days: Decimal


async def balance_lines(
    db: AsyncSession, org_id: uuid.UUID, persons: Sequence[Person], year_for: YearFor
) -> dict[uuid.UUID, PersonBalances]:
    """``{user_id: balances}`` for each person with a policy; ``year_for`` picks the year."""
    persons = [p for p in persons if p.policy is not None]
    if not persons:
        return {}
    policies = {p.policy.id: p.policy for p in persons if p.policy}
    years = {pid: year_for(policy) for pid, policy in policies.items()}
    types = await LeaveTypeRepository(db, org_id=org_id).list_for_policies(
        policies, active_only=True
    )
    users = {p.user_id for p in persons}
    type_ids = {t.id for per in types.values() for t in per}
    first = min(y.start for y in years.values())
    last = max(y.end for y in years.values())
    ledger = await LeaveLedgerRepository(db, org_id=org_id).type_totals(users, type_ids)
    usage_repo = LeaveUsageRepository(db, org_id=org_id)
    year_of = {p.user_id: years[p.policy.id] for p in persons if p.policy}
    bookings: dict[tuple[uuid.UUID, uuid.UUID], list[Booking]] = defaultdict(list)
    for user, type_id, status, start, days in await usage_repo.leave_days_by_start(
        users, type_ids, first, last
    ):
        if year_of[user].start <= start <= year_of[user].end:
            bookings[(user, type_id)].append(booking(status, start, days))
    lop: dict[uuid.UUID, Decimal] = defaultdict(Decimal)
    for user, start, days in await usage_repo.lop_by_start(users, first, last):
        if year_of[user].start <= start <= year_of[user].end:
            lop[user] += days
    out: dict[uuid.UUID, PersonBalances] = {}
    for p in persons:
        if p.policy is None:
            continue
        year, rule = years[p.policy.id], proration_rule(p.policy)
        # Read as of today (a past year at its end): what is earned and still
        # bookable now, with leave booked ahead counted in its own month.
        on = day_in_year(today_for(p.policy), year)
        lines = []
        for t in usable_types(types.get(p.policy.id, []), p.profile):
            stored, adjustments = ledger.get((p.user_id, t.id, year.label), (None, ZERO))
            lines.append(
                build_line(
                    t,
                    stored,
                    adjustments,
                    bookings[(p.user_id, t.id)],
                    profile=p.profile,
                    year=year,
                    rule=rule,
                    on=on,
                )  # fmt: skip
            )
        out[p.user_id] = PersonBalances(year=year, lines=lines, lop_days=lop[p.user_id])
    return out
