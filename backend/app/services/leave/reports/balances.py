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

"""Balances for everyone in scope for one leave year, in a fixed number of queries.

Each member's year is their own policy's leave year with the requested
label (the current one by default). Numbers match the Leave page: they come
from the same :func:`build_line`, read-only, so a report never freezes an
allocation in the ledger.
"""

import uuid
from collections import defaultdict
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.leave_policy import LeavePolicy
from app.models.leave_request import LeaveStatus
from app.models.leave_type import LeaveType
from app.repositories.leave_ledger import LeaveLedgerRepository
from app.repositories.leave_type import LeaveTypeRepository
from app.repositories.leave_usage import LeaveUsageRepository
from app.schemas.leave_report_filters import BalanceFilters
from app.schemas.leave_reports import BalanceReport, BalanceRow
from app.services.leave.balances import build_line, proration_rule
from app.services.leave.calendar_math import (
    LeaveYearBounds,
    leave_year_bounds,
    leave_year_by_label,
)
from app.services.leave.policies import today_for
from app.services.leave.report_scope import ReportScope
from app.services.leave.reports.population import people, scoped_ids

ZERO = Decimal("0")


def _year(policy: LeavePolicy, label: int | None) -> LeaveYearBounds:
    if label is not None:
        return leave_year_by_label(label, policy.year_start_month)
    return leave_year_bounds(today_for(policy), policy.year_start_month)


async def balance_report(
    db: AsyncSession, org_id: uuid.UUID, scope: ReportScope, f: BalanceFilters
) -> BalanceReport:
    """One row per member per active leave type on their policy."""
    ids = await scoped_ids(db, org_id, scope, f)
    persons = [p for p in await people(db, org_id, ids, f) if p.policy is not None]
    if not persons:
        return BalanceReport(rows=[])
    policies = {p.policy.id: p.policy for p in persons if p.policy}
    years = {pid: _year(policy, f.year) for pid, policy in policies.items()}
    type_repo = LeaveTypeRepository(db, org_id=org_id)
    types: dict[uuid.UUID, list[LeaveType]] = {
        pid: await type_repo.list_for_policy(pid, active_only=True) for pid in policies
    }
    users = {p.user_id for p in persons}
    type_ids = {t.id for per in types.values() for t in per}
    first = min(y.start for y in years.values())
    last = max(y.end for y in years.values())
    ledger = await LeaveLedgerRepository(db, org_id=org_id).type_totals(users, type_ids)
    usage_repo = LeaveUsageRepository(db, org_id=org_id)
    year_of = {p.user_id: years[p.policy.id] for p in persons if p.policy}
    used: dict[tuple[uuid.UUID, uuid.UUID], list[Decimal]] = defaultdict(lambda: [ZERO, ZERO])
    for user, type_id, status, start, days in await usage_repo.leave_days_by_start(
        users, type_ids, first, last
    ):
        if year_of[user].start <= start <= year_of[user].end:
            used[(user, type_id)][0 if status == LeaveStatus.APPROVED else 1] += days
    lop: dict[uuid.UUID, Decimal] = defaultdict(Decimal)
    for user, start, days in await usage_repo.lop_by_start(users, first, last):
        if year_of[user].start <= start <= year_of[user].end:
            lop[user] += days
    rows = []
    for p in persons:
        if p.policy is None:
            continue
        year, rule = years[p.policy.id], proration_rule(p.policy)
        for t in types[p.policy.id]:
            stored, adjustments = ledger.get((p.user_id, t.id, year.label), (None, ZERO))
            approved, pending = used[(p.user_id, t.id)]
            line = build_line(
                t, stored, adjustments, approved, pending, profile=p.profile, year=year, rule=rule
            )
            rows.append(
                BalanceRow(
                    **p.columns.model_dump(),
                    leave_year=year.label,
                    leave_type=t.name,
                    allocated=line.allocated,
                    adjustments=line.adjustments,
                    used=line.used,
                    pending=line.pending,
                    available=line.available,
                    lop_days=lop[p.user_id],
                )
            )
    return BalanceReport(rows=rows)
