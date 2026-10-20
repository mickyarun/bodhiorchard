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
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee_profile import WorkArrangement
from app.models.leave_request import LeaveKind
from app.schemas.leave import LeaveRequestCreate
from app.services.leave.approvers import approvers_for, notify_targets
from app.services.leave.calendar_math import count_days
from app.services.leave.date_rules import date_problems
from app.services.leave.evaluation_steps import (
    Evaluation,
    apply_balance,
    apply_optional_holiday,
    check_overlap,
)
from app.services.leave.policies import MemberPolicy, mandatory_holidays, today_for
from app.services.leave.wfh_usage import wfh_auto_approved

ZERO = Decimal("0")


async def evaluate(
    db: AsyncSession,
    *,
    member: MemberPolicy,
    user_id: uuid.UUID,
    body: LeaveRequestCreate,
    persist: bool = False,
) -> Evaluation:
    """Check every rule for ``body`` and price it.

    ``persist`` lets a real submit write the year's allocation for the
    requested type to the ledger; a preview only computes it.
    """
    policy = member.policy
    result = Evaluation(start=body.start_date, end=body.end_date)
    profile = member.profile
    if (
        body.kind == LeaveKind.WFH
        and profile
        and profile.work_arrangement == WorkArrangement.REMOTE
    ):
        # Home is their normal place of work: nothing to request.
        result.problem("remote_no_wfh", "You work remotely, so there's no need to request WFH.")
        return result
    if body.kind == LeaveKind.OPTIONAL_HOLIDAY:
        await apply_optional_holiday(db, member.policy, user_id, body, result)
    problems = date_problems(
        result.start,
        result.end,
        today=today_for(policy),
        backdate_limit_days=policy.backdate_limit_days,
        year_start_month=policy.year_start_month,
    )
    for code, message in problems:
        result.problem(code, message)
    # Dates that can't be requested at all: don't count days or check
    # balances for them.
    if problems:
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
    await check_overlap(db, policy.org_id, user_id, result, body.half_day)
    if body.kind == LeaveKind.LEAVE and body.leave_type_id is not None:
        await apply_balance(db, member, user_id, body.leave_type_id, result, persist)
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
