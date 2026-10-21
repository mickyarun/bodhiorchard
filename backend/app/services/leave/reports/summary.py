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

"""Employee-wise leave taken in a date range (approved), plus what is pending.

Days are the part of each request inside the range (see ``attribution``),
so a month's report shows that month's leave even when it spans a month end.
These are "taken in range", not the leave-year "used" that balances show.
"""

import uuid
from collections import defaultdict
from collections.abc import Sequence
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.leave_request import LeaveKind, LeaveRequest, LeaveStatus
from app.models.leave_type import LeaveType
from app.repositories.leave_policy import LeavePolicyRepository
from app.repositories.leave_report import LeaveReportRepository
from app.repositories.leave_request import ACTIVE
from app.repositories.leave_request_filter import RequestFilter
from app.repositories.leave_type import LeaveTypeRepository
from app.schemas.leave_report_filters import SummaryFilters
from app.schemas.leave_reports import NamedRef, SummaryReport, SummaryRow
from app.services.leave.calendar_math import leave_year_bounds
from app.services.leave.errors import LeaveInvalidError
from app.services.leave.high_leave import assess, taken_this_year
from app.services.leave.policies import mandatory_holidays
from app.services.leave.report_scope import ReportScope
from app.services.leave.reports.attribution import InRange, Span, within
from app.services.leave.reports.balance_lines import balance_lines
from app.services.leave.reports.population import Person, people, scoped_ids
from app.services.leave.reports.type_columns import type_columns
from app.services.leave.type_privacy import shown, visible

REQUEST_CAP = 20_000
ZERO = Decimal("0")
UNKNOWN_POLICY = "other policy"


async def _in_range(
    db: AsyncSession, org_id: uuid.UUID, requests: Sequence[LeaveRequest], f: SummaryFilters
) -> dict[uuid.UUID, InRange]:
    """Each request's days inside the range, recounting only those that cross an edge."""
    crossing = [r for r in requests if r.start_date < f.start or r.end_date > f.end]
    policies = await LeavePolicyRepository(db, org_id=org_id).by_ids(
        {r.policy_id for r in crossing}
    )
    holidays: dict[uuid.UUID, dict[date, str]] = {}
    for policy in policies.values():
        own = [r for r in crossing if r.policy_id == policy.id]
        first, last = min(r.start_date for r in own), max(r.end_date for r in own)
        holidays[policy.id] = await mandatory_holidays(db, policy, first, last)
    out = {r.id: InRange(r.days, r.lop_days) for r in requests}
    for r in crossing:
        # policy_id is required and org-scoped, so the policy is always found.
        booked = policies[r.policy_id]
        out[r.id] = within(
            Span(r.start_date, r.end_date, r.days, r.lop_days),
            f.start,
            f.end,
            working_days=booked.working_days,
            holidays=holidays[r.policy_id],
        )
    return out


async def _hidden_types(
    db: AsyncSession, org_id: uuid.UUID, requests: Sequence[LeaveRequest], sees_all: bool
) -> set[uuid.UUID]:
    """Ids of the requests' types the viewer may not see."""
    if sees_all:
        return set()
    ids = {r.leave_type_id for r in requests if r.leave_type_id}
    types = await LeaveTypeRepository(db, org_id=org_id).by_ids(ids)
    return {i for i, t in types.items() if not shown(t, sees_all=False)}


async def _types(
    db: AsyncSession, org_id: uuid.UUID, persons: Sequence[Person], used: set[uuid.UUID]
) -> list[LeaveType]:
    """Types on the members' policies plus any type their leave used."""
    repo = LeaveTypeRepository(db, org_id=org_id)
    found = dict(await repo.by_ids(used))
    policy_ids = {p.policy.id for p in persons if p.policy}
    for per in (await repo.list_for_policies(policy_ids, active_only=True)).values():
        for leave_type in per:
            found.setdefault(leave_type.id, leave_type)
    return sorted(found.values(), key=lambda t: t.name.lower())


def type_refs(types: Sequence[LeaveType], policy_names: dict[uuid.UUID, str]) -> list[NamedRef]:
    """Type columns; a name used by two policies gets the policy added."""
    seen: dict[str, int] = defaultdict(int)
    for t in types:
        seen[t.name] += 1
    return [
        NamedRef(
            id=t.id,
            name=f"{t.name} ({policy_names.get(t.policy_id, UNKNOWN_POLICY)})"
            if seen[t.name] > 1
            else t.name,
        )
        for t in types
    ]


async def summary_report(
    db: AsyncSession, org_id: uuid.UUID, scope: ReportScope, f: SummaryFilters
) -> SummaryReport:
    """One row per member in scope (and anyone who took leave without a profile)."""
    ids = await scoped_ids(db, org_id, scope, f)
    requests = await LeaveReportRepository(db, org_id=org_id).overlapping(
        ids, f.start, f.end, RequestFilter(statuses=ACTIVE), limit=REQUEST_CAP + 1
    )
    if len(requests) > REQUEST_CAP:
        raise LeaveInvalidError("Too much leave in this range. Narrow the dates or filters.")
    persons = await people(db, org_id, ids, f, requesters={r.user_id for r in requests})
    wanted = {p.user_id for p in persons}
    # A hidden type's days are left out of every figure, totals included:
    # otherwise total minus the visible columns would give them away.
    hidden = await _hidden_types(db, org_id, requests, scope.sees_restricted)
    requests = [r for r in requests if r.user_id in wanted and r.leave_type_id not in hidden]
    parts = await _in_range(db, org_id, requests, f)
    sums: dict[uuid.UUID, dict[str, Decimal]] = defaultdict(lambda: defaultdict(lambda: ZERO))
    by_type: dict[uuid.UUID, dict[uuid.UUID, Decimal]] = defaultdict(
        lambda: defaultdict(lambda: ZERO)
    )
    for r in requests:
        part, row = parts[r.id], sums[r.user_id]
        if r.status == LeaveStatus.PENDING:
            # Pending leave only: pending WFH isn't time off.
            if r.kind == LeaveKind.LEAVE:
                row["pending"] += part.days
        elif r.kind == LeaveKind.WFH:
            row["wfh"] += part.days
        elif r.kind == LeaveKind.OPTIONAL_HOLIDAY:
            row["optional"] += part.days
        else:
            row["leave"] += part.days
            row["lop"] += part.lop_days
            if r.leave_type_id is not None:
                by_type[r.user_id][r.leave_type_id] += part.days
    # "Left" is for the leave year the range ends in, on each member's policy.
    balances = await balance_lines(
        db, org_id, persons, lambda policy: leave_year_bounds(f.end, policy.year_start_month)
    )
    left = {
        user: {line.leave_type.id: line.available for line in mine.lines}
        for user, mine in balances.items()
    }
    # Heads-up / warning per person, for the leave year the range ends in.
    taken = await taken_this_year(db, [(p.user_id, p.policy) for p in persons if p.policy], f.end)
    policy_of = {p.user_id: p.policy for p in persons if p.policy}
    high = {
        user: level
        for user, days in taken.items()
        if (level := assess(policy_of[user], days)) is not None
    }
    used = {t for per in by_type.values() for t in per}
    # Hidden types get no column, and no "left" figure.
    types = visible(
        await _types(db, org_id, persons, used), lambda t: t, sees_all=scope.sees_restricted
    )
    columns = type_columns(types)
    shown_ids = set(columns.key_of)
    left = {user: {t: d for t, d in per.items() if t in shown_ids} for user, per in left.items()}
    return SummaryReport(
        start=f.start,
        end=f.end,
        leave_types=columns.refs,
        rows=[
            SummaryRow(
                **p.columns.model_dump(),
                leave_by_type=columns.taken(by_type.get(p.user_id, {})),
                left_by_type=columns.left(left.get(p.user_id, {})),
                leave_days=sums[p.user_id]["leave"],
                high_leave=high.get(p.user_id),
                lop_days=sums[p.user_id]["lop"],
                wfh_days=sums[p.user_id]["wfh"],
                optional_holidays=sums[p.user_id]["optional"],
                pending_days=sums[p.user_id]["pending"],
            )
            for p in persons
        ],
    )
