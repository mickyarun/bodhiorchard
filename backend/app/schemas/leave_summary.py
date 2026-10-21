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
"""DTOs for a member's leave overview: policy, leave year and balances."""

import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel

from app.models.employee_profile import WorkArrangement
from app.models.leave_policy import WfhApproval
from app.models.leave_type import LeaveAccrual
from app.schemas.leave import HolidayRead, LeaveTypeBrief, PersonRef


class LeaveYear(BaseModel):
    """A leave year: label is the calendar year it starts in."""

    label: int
    start: date
    end: date


class PolicyBrief(BaseModel):
    """The rules a member's requests follow."""

    id: uuid.UUID
    name: str
    timezone: str
    working_days: list[int]
    year_start_month: int
    wfh_approval: WfhApproval
    wfh_monthly_auto_days: int
    backdate_limit_days: int
    optional_holiday_quota: int


class Balance(BaseModel):
    """One leave type's balance for one leave year. None = no limit."""

    leave_type: LeaveTypeBrief
    is_paid: bool
    accrual: LeaveAccrual
    allocated: Decimal | None
    # Of ``allocated``, what is released so far (all of it when upfront).
    earned: Decimal | None
    adjustments: Decimal
    used: Decimal
    pending: Decimal
    available: Decimal | None


class OptionalHolidayBalance(BaseModel):
    """Optional holidays: quota, use, and the ones still available to pick."""

    quota: int
    used: int
    pending: int
    remaining: int
    holidays: list[HolidayRead]


class LeaveSummary(BaseModel):
    """Everything the Leave home page needs for the caller."""

    policy: PolicyBrief
    leave_year: LeaveYear
    balances: list[Balance]
    optional_holidays: OptionalHolidayBalance
    wfh_auto_days_left_this_month: int | None
    # Leave days this leave year (approved or pending) past the balance.
    lop_days: Decimal
    approvers: list[PersonRef]
    # True when no active manager is set: requests go to HR.
    routes_to_hr: bool
    # Remote people don't request WFH, so the page hides it for them.
    work_arrangement: WorkArrangement
