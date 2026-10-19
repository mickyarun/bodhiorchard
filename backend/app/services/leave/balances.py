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

Allocations are written to the ledger the first time a year is read
(:func:`app.services.leave.allocation.allocation_for_year`), which freezes
them: a later quota edit doesn't rewrite a year already in use.
"""

import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee_profile import EmployeeProfile
from app.models.leave_policy import LeavePolicy
from app.models.leave_type import LeaveType
from app.repositories.leave_ledger import LeaveLedgerRepository
from app.repositories.leave_request import LeaveRequestRepository
from app.repositories.leave_type import LeaveTypeRepository
from app.services.leave.allocation import allocation_for_year
from app.services.leave.calendar_math import LeaveYearBounds
from app.services.leave.policies import effective_from

ZERO = Decimal("0")


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


async def balances_for(
    db: AsyncSession,
    *,
    policy: LeavePolicy,
    profile: EmployeeProfile | None,
    user_id: uuid.UUID,
    year: LeaveYearBounds,
) -> list[BalanceLine]:
    """Balances for every active leave type on ``policy``."""
    org_id = policy.org_id
    types = await LeaveTypeRepository(db, org_id=org_id).list_for_policy(
        policy.id, active_only=True
    )
    ledger = LeaveLedgerRepository(db, org_id=org_id)
    totals = await ledger.totals(user_id, year.label)
    for leave_type in types:
        quota = leave_type.annual_quota_days
        if quota is not None and totals.get(leave_type.id, (None, ZERO))[0] is None:
            days = allocation_for_year(quota, effective_from(profile), year.start, year.end)
            await ledger.ensure_allocation(user_id, leave_type.id, year.label, days)
    totals = await ledger.totals(user_id, year.label)
    usage = await LeaveRequestRepository(db, org_id=org_id).leave_day_totals(
        user_id, year.start, year.end
    )
    lines = []
    for leave_type in types:
        allocated, adjustments = totals.get(leave_type.id, (None, ZERO))
        used, pending = usage.get(leave_type.id, (ZERO, ZERO))
        lines.append(
            BalanceLine(
                leave_type=leave_type,
                allocated=allocated if leave_type.annual_quota_days is not None else None,
                adjustments=adjustments,
                used=used,
                pending=pending,
            )
        )
    return lines


def find_line(lines: list[BalanceLine], leave_type_id: uuid.UUID) -> BalanceLine | None:
    """The balance for one type, if it's on the list."""
    return next((line for line in lines if line.leave_type.id == leave_type_id), None)
