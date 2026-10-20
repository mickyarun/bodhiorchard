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

"""The pieces of a request evaluation: the result and its separate checks.

:func:`app.services.leave.evaluation.evaluate` runs them in order; each
records what it finds on the shared :class:`Evaluation`.
"""

import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.leave_policy import LeavePolicy
from app.models.leave_request import HalfDay, LeaveRequest
from app.models.policy_holiday import PolicyHoliday
from app.repositories.leave_request import LeaveRequestRepository
from app.repositories.leave_type import LeaveTypeRepository
from app.schemas.leave import LeaveProblem, LeaveRequestCreate, ProblemCode
from app.services.leave.approvers import Approvers
from app.services.leave.balances import balances_for, find_line
from app.services.leave.calendar_math import leave_year_bounds
from app.services.leave.loss_of_pay import split_paid
from app.services.leave.optional_holidays import pick_optional_holiday
from app.services.leave.policies import MemberPolicy

ZERO = Decimal("0")


@dataclass
class Evaluation:
    """The outcome of evaluating one request."""

    start: date
    end: date
    days: Decimal = ZERO
    excluded: list[tuple[date, str]] = field(default_factory=list)
    balance_before: Decimal | None = None
    # Days the balance doesn't cover; they're taken as loss of pay.
    lop_days: Decimal = ZERO
    holiday: PolicyHoliday | None = None
    auto_approved: bool = False
    approvers: Approvers = field(default_factory=lambda: Approvers(managers=[]))
    problems: list[LeaveProblem] = field(default_factory=list)

    @property
    def balance_after(self) -> Decimal | None:
        """Balance once this request is counted."""
        if self.balance_before is None:
            return None
        return self.balance_before - (self.days - self.lop_days)

    def problem(self, code: ProblemCode, message: str) -> None:
        """Record a reason the request can't be sent."""
        self.problems.append(LeaveProblem(code=code, message=message))


async def apply_optional_holiday(
    db: AsyncSession,
    policy: LeavePolicy,
    user_id: uuid.UUID,
    body: LeaveRequestCreate,
    result: Evaluation,
) -> None:
    """Pin an optional-holiday request to its holiday and check the quota."""
    pick = await pick_optional_holiday(db, policy, user_id, body.holiday_id)
    if pick.holiday is None:
        result.problem("holiday_not_optional", "Pick one of your policy's optional holidays.")
        return
    result.holiday = pick.holiday
    result.start = result.end = pick.holiday.date
    result.days = Decimal("1")
    if pick.remaining <= 0:
        result.problem(
            "optional_quota_used",
            f"You've used all {policy.optional_holiday_quota} optional holidays this year.",
        )


def _other_half(existing: LeaveRequest, start: date, end: date, half_day: HalfDay) -> bool:
    """True when both are single-day half days on different halves (no clash)."""
    single_day = existing.start_date == existing.end_date == start == end
    halves = (existing.half_day, half_day)
    return single_day and HalfDay.NONE not in halves and halves[0] != halves[1]


async def check_overlap(
    db: AsyncSession,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    result: Evaluation,
    half_day: HalfDay,
) -> None:
    """Refuse dates already covered by another pending or approved request.

    A morning and an afternoon of the same day don't clash.
    """
    clashes = [
        clash
        for clash in await LeaveRequestRepository(db, org_id=org_id).active_between(
            [user_id], result.start, result.end
        )
        if not _other_half(clash, result.start, result.end, half_day)
    ]
    if clashes:
        first = clashes[0]
        when = f"{first.start_date:%a %d %b}"
        result.problem(
            "overlap",
            f"You already have a {first.status.value} request covering {when}. "
            "Change your dates or cancel that request first.",
        )


async def apply_balance(
    db: AsyncSession,
    member: MemberPolicy,
    user_id: uuid.UUID,
    leave_type_id: uuid.UUID,
    result: Evaluation,
    persist: bool,
) -> None:
    """Price a leave request against the type's balance for its leave year.

    Days past the balance aren't refused: they're loss of pay.
    """
    policy = member.policy
    leave_type = await LeaveTypeRepository(db, org_id=policy.org_id).get_by_id(leave_type_id)
    if leave_type is None or leave_type.policy_id != policy.id or not leave_type.is_active:
        result.problem("inactive_type", "That leave type isn't available on your policy.")
        return
    year = leave_year_bounds(result.start, policy.year_start_month)
    lines = await balances_for(
        db,
        policy=policy,
        profile=member.profile,
        user_id=user_id,
        year=year,
        persist_type_id=leave_type_id if persist else None,
    )
    line = find_line(lines, leave_type_id)
    result.balance_before = line.available if line else None
    _paid, result.lop_days = split_paid(result.days, result.balance_before)
