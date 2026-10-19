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

"""The caller's leave overview: policy, balances, optional holidays, WFH left."""

import uuid
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.leave_policy import LeavePolicy
from app.models.policy_holiday import PolicyHoliday
from app.schemas.leave import HolidayRead, LeaveTypeBrief, PersonRef
from app.schemas.leave_summary import (
    Balance,
    LeaveSummary,
    LeaveYear,
    OptionalHolidayBalance,
    PolicyBrief,
)
from app.services.leave.approvers import approvers_for
from app.services.leave.balances import BalanceLine, balances_for
from app.services.leave.calendar_math import (
    LeaveYearBounds,
    leave_year_bounds,
    leave_year_by_label,
)
from app.services.leave.optional_holidays import optional_holiday_use
from app.services.leave.policies import resolve_member_policy, today_for
from app.services.leave.wfh_policy import auto_days_left
from app.services.leave.wfh_usage import wfh_days_by_month


def balance_schema(line: BalanceLine) -> Balance:
    """Wire shape of one balance line."""
    t = line.leave_type
    return Balance(
        leave_type=LeaveTypeBrief(id=t.id, name=t.name, code=t.code, color_key=t.color_key),
        is_paid=t.is_paid,
        allocated=line.allocated,
        adjustments=line.adjustments,
        used=line.used,
        pending=line.pending,
        available=line.available,
    )


def year_schema(year: LeaveYearBounds) -> LeaveYear:
    """Wire shape of a leave year."""
    return LeaveYear(label=year.label, start=year.start, end=year.end)


def holiday_schema(holiday: PolicyHoliday) -> HolidayRead:
    """Wire shape of a holiday."""
    return HolidayRead(id=holiday.id, date=holiday.date, name=holiday.name, kind=holiday.kind)


def policy_brief(policy: LeavePolicy) -> PolicyBrief:
    """Wire shape of the rules a member follows."""
    return PolicyBrief(
        id=policy.id,
        name=policy.name,
        timezone=policy.timezone,
        working_days=list(policy.working_days),
        year_start_month=policy.year_start_month,
        wfh_approval=policy.wfh_approval,
        wfh_monthly_auto_days=policy.wfh_monthly_auto_days,
        backdate_limit_days=policy.backdate_limit_days,
        optional_holiday_quota=policy.optional_holiday_quota,
    )


async def build_summary(
    db: AsyncSession, org_id: uuid.UUID, user_id: uuid.UUID, year_label: int | None
) -> LeaveSummary:
    """Everything the Leave home page shows for ``user_id``."""
    member = await resolve_member_policy(db, org_id, user_id)
    policy = member.policy
    today = today_for(policy)
    year = (
        leave_year_by_label(year_label, policy.year_start_month)
        if year_label
        else leave_year_bounds(today, policy.year_start_month)
    )
    lines = await balances_for(
        db, policy=policy, profile=member.profile, user_id=user_id, year=year
    )
    optional = await optional_holiday_use(db, policy, user_id, year.start)
    used_now = (await wfh_days_by_month(db, policy, user_id, today, today)).get(
        (today.year, today.month)
    )
    approvers = await approvers_for(db, org_id, user_id)
    return LeaveSummary(
        policy=policy_brief(policy),
        leave_year=year_schema(year),
        balances=[balance_schema(line) for line in lines],
        optional_holidays=OptionalHolidayBalance(
            quota=optional.quota,
            used=optional.used,
            pending=optional.pending,
            remaining=optional.remaining,
            holidays=[holiday_schema(h) for h in optional.available if h.date >= today],
        ),
        wfh_auto_days_left_this_month=auto_days_left(
            policy.wfh_approval, policy.wfh_monthly_auto_days, used_now or Decimal("0")
        ),
        approvers=[PersonRef(user_id=uid, name=name) for uid, name in approvers.managers],
        routes_to_hr=approvers.routes_to_hr,
    )
