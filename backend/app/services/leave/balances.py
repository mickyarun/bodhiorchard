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

"""Leave balances: allocation + adjustments − approved − pending.

A year's allocation (:func:`app.services.leave.allocation.allocation_for_year`)
is written to the ledger on the member's first submit or approval in that
year, which freezes it: a later quota or proration edit doesn't rewrite a
year already in use. Until then it is worked out live from the policy.
"""

import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee_profile import EmployeeProfile
from app.models.leave_policy import LeavePolicy
from app.models.leave_type import LeaveType
from app.repositories.leave_ledger import LeaveLedgerRepository
from app.repositories.leave_type import LeaveTypeRepository
from app.repositories.leave_usage import LeaveUsageRepository
from app.services.leave.allocation import ProrationRule, allocation_for_year
from app.services.leave.calendar_math import LeaveYearBounds
from app.services.leave.policies import effective_from

ZERO = Decimal("0")


def proration_rule(policy: LeavePolicy) -> ProrationRule:
    """The policy's settings for prorating a part-year allocation."""
    return ProrationRule(
        method=policy.proration_method,
        cutoff_day=policy.proration_cutoff_day,
        rounding=policy.allocation_rounding,
    )


@dataclass(frozen=True)
class BalanceLine:
    """One leave type's numbers for one year. None = no limit."""

    leave_type: LeaveType
    allocated: Decimal | None
    adjustments: Decimal
    used: Decimal
    pending: Decimal

    @property
    def available(self) -> Decimal | None:
        """Days still free to request, counting pending requests as taken."""
        if self.allocated is None:
            return None
        return self.allocated + self.adjustments - self.used - self.pending


def build_line(
    leave_type: LeaveType,
    stored: Decimal | None,
    adjustments: Decimal,
    used: Decimal,
    pending: Decimal,
    *,
    profile: EmployeeProfile | None,
    year: LeaveYearBounds,
    rule: ProrationRule,
) -> BalanceLine:
    """One type's balance; a year with no stored allocation gets one worked out live."""
    quota = leave_type.annual_quota_days
    allocated = stored
    if quota is None:
        allocated = None
    elif stored is None:
        allocated = allocation_for_year(quota, effective_from(profile), year.start, year.end, rule)
    return BalanceLine(
        leave_type=leave_type,
        allocated=allocated,
        adjustments=adjustments,
        used=used,
        pending=pending,
    )


async def balances_for(
    db: AsyncSession,
    *,
    policy: LeavePolicy,
    profile: EmployeeProfile | None,
    user_id: uuid.UUID,
    year: LeaveYearBounds,
    persist_type_id: uuid.UUID | None = None,
) -> list[BalanceLine]:
    """Balances for every active leave type on ``policy``.

    A year with no allocation yet gets one computed from the current quota
    and proration rule. Only ``persist_type_id`` (the type a real submit or
    approval is spending) is written to the ledger and so frozen; other
    types, and plain reads — the Leave page, a preview, the approvals
    queue — never lock in a year early.
    """
    org_id = policy.org_id
    types = await LeaveTypeRepository(db, org_id=org_id).list_for_policy(
        policy.id, active_only=True
    )
    ledger = LeaveLedgerRepository(db, org_id=org_id)
    totals = await ledger.totals(user_id, year.label)
    rule = proration_rule(policy)
    persist = next((t for t in types if t.id == persist_type_id), None)
    if persist is not None and persist.annual_quota_days is not None:
        stored, adjustments = totals.get(persist.id, (None, ZERO))
        if stored is None:
            joined = effective_from(profile)
            days = allocation_for_year(
                persist.annual_quota_days, joined, year.start, year.end, rule
            )
            # Callers hold the member's lock, so nobody else writes it meanwhile.
            await ledger.ensure_allocation(user_id, persist.id, year.label, days)
            totals[persist.id] = (days, adjustments)
    usage = await LeaveUsageRepository(db, org_id=org_id).leave_day_totals(
        user_id, year.start, year.end
    )
    return [
        build_line(
            t,
            *totals.get(t.id, (None, ZERO)),
            *usage.get(t.id, (ZERO, ZERO)),
            profile=profile,
            year=year,
            rule=rule,
        )
        for t in types
    ]


def find_line(lines: list[BalanceLine], leave_type_id: uuid.UUID) -> BalanceLine | None:
    """The balance for one type, if it's on the list."""
    return next((line for line in lines if line.leave_type.id == leave_type_id), None)
