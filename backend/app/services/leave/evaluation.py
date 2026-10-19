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

"""Evaluate a leave/WFH/optional-holiday request before it's saved.

One pass produces everything the request dialog shows (days, exclusions,
balance before and after, approvers, auto-approval) and every reason it
can't be sent. Submit runs the same evaluation again under the member's
row lock, so the preview and the real check never disagree.
"""

import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.leave_policy import LeavePolicy
from app.models.leave_request import LeaveKind
from app.models.policy_holiday import PolicyHoliday
from app.repositories.leave_request import LeaveRequestRepository
from app.repositories.leave_type import LeaveTypeRepository
from app.schemas.leave import LeaveProblem, LeaveRequestCreate, ProblemCode
from app.services.leave.approvers import Approvers, approvers_for, notify_targets
from app.services.leave.balances import balances_for, find_line
from app.services.leave.calendar_math import count_days, leave_year_bounds
from app.services.leave.date_rules import date_problems
from app.services.leave.optional_holidays import pick_optional_holiday
from app.services.leave.policies import MemberPolicy, mandatory_holidays, today_for
from app.services.leave.wfh_usage import wfh_auto_approved

ZERO = Decimal("0")


@dataclass
class Evaluation:
    """The outcome of evaluating one request."""

    start: date
    end: date
    days: Decimal = ZERO
    excluded: list[tuple[date, str]] = field(default_factory=list)
    balance_before: Decimal | None = None
    holiday: PolicyHoliday | None = None
    auto_approved: bool = False
    approvers: Approvers = field(default_factory=lambda: Approvers(managers=[]))
    problems: list[LeaveProblem] = field(default_factory=list)

    @property
    def balance_after(self) -> Decimal | None:
        """Balance once this request is counted."""
        return None if self.balance_before is None else self.balance_before - self.days

    def problem(self, code: ProblemCode, message: str) -> None:
        """Record a reason the request can't be sent."""
        self.problems.append(LeaveProblem(code=code, message=message))


async def evaluate(
    db: AsyncSession,
    *,
    member: MemberPolicy,
    user_id: uuid.UUID,
    body: LeaveRequestCreate,
    exclude_request: uuid.UUID | None = None,
    persist: bool = False,
) -> Evaluation:
    """Check every rule for ``body`` and price it.

    ``persist`` lets a real submit write the year's allocation to the
    ledger; a preview only computes it.
    """
    policy = member.policy
    result = Evaluation(start=body.start_date, end=body.end_date)
    if body.kind == LeaveKind.OPTIONAL_HOLIDAY:
        await _apply_optional_holiday(db, member.policy, user_id, body, result)
    problems = date_problems(
        result.start,
        result.end,
        today=today_for(policy),
        backdate_limit_days=policy.backdate_limit_days,
        year_start_month=policy.year_start_month,
    )
    for code, message in problems:
        result.problem(code, message)
    if any(code == "too_far_ahead" for code, _ in problems):
        return result
    if body.kind != LeaveKind.OPTIONAL_HOLIDAY:
        holidays = await mandatory_holidays(db, policy, result.start, result.end)
        counted = count_days(
            result.start,
            result.end,
            body.half_day,
            working_days=policy.working_days,
            holidays=holidays,
        )
        result.days, result.excluded = counted.days, counted.excluded
        if result.days == ZERO:
            result.problem("no_working_days", "These dates are all weekends or holidays.")
    await _check_overlap(db, policy.org_id, user_id, result, exclude_request)
    if body.kind == LeaveKind.LEAVE and body.leave_type_id is not None:
        await _apply_balance(db, member, user_id, body.leave_type_id, result, persist)
    if body.kind == LeaveKind.WFH:
        result.auto_approved = await wfh_auto_approved(
            db, member.policy, user_id, result.start, result.end, body.half_day
        )
    result.approvers = await approvers_for(db, policy.org_id, user_id)
    if not result.auto_approved and not await notify_targets(
        db, policy.org_id, result.approvers, user_id
    ):
        result.problem(
            "no_approver",
            "Nobody can approve this yet: you have no manager and no one else has the HR role. "
            "Ask the org owner to set your manager or give someone the HR role.",
        )
    return result


async def _apply_optional_holiday(
    db: AsyncSession,
    policy: LeavePolicy,
    user_id: uuid.UUID,
    body: LeaveRequestCreate,
    result: Evaluation,
) -> None:
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


async def _check_overlap(
    db: AsyncSession,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    result: Evaluation,
    exclude: uuid.UUID | None,
) -> None:
    clashes = await LeaveRequestRepository(db, org_id=org_id).active_between(
        [user_id], result.start, result.end, exclude=exclude
    )
    if clashes:
        first = clashes[0]
        when = f"{first.start_date:%a %d %b}"
        result.problem(
            "overlap",
            f"You already have a {first.status.value} request covering {when}. "
            "Change your dates or cancel that request first.",
        )


async def _apply_balance(
    db: AsyncSession,
    member: MemberPolicy,
    user_id: uuid.UUID,
    leave_type_id: uuid.UUID,
    result: Evaluation,
    persist: bool,
) -> None:
    policy = member.policy
    leave_type = await LeaveTypeRepository(db, org_id=policy.org_id).get_by_id(leave_type_id)
    if leave_type is None or leave_type.policy_id != policy.id or not leave_type.is_active:
        result.problem("inactive_type", "That leave type isn't available on your policy.")
        return
    year = leave_year_bounds(result.start, policy.year_start_month)
    lines = await balances_for(
        db, policy=policy, profile=member.profile, user_id=user_id, year=year, persist=persist
    )
    line = find_line(lines, leave_type_id)
    result.balance_before = line.available if line else None
    if result.balance_after is not None and result.balance_after < ZERO:
        result.problem(
            "insufficient_balance",
            f"Not enough {leave_type.name}: this needs {result.days} days and you have "
            f"{result.balance_before} left.",
        )
