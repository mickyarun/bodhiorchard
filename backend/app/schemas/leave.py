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

"""DTOs for leave, WFH and optional-holiday requests, balances and approvals.

Leave type and reason are privacy-sensitive (sick leave). They appear only
in responses for the requester, their managers and HR; the team calendar
gives everyone else just "on leave".
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.models.leave_policy import WfhApproval
from app.models.leave_request import ApprovalMode, HalfDay, LeaveKind, LeaveStatus
from app.models.policy_holiday import HolidayKind


class LeaveTypeBrief(BaseModel):
    """Leave type as shown on a request."""

    id: uuid.UUID
    name: str
    code: str
    color_key: str


class HolidayRead(BaseModel):
    """One holiday on a policy calendar."""

    id: uuid.UUID
    date: date
    name: str
    kind: HolidayKind


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
    allocated: Decimal | None
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


class PersonRef(BaseModel):
    """A member by id and name."""

    user_id: uuid.UUID
    name: str


class LeaveSummary(BaseModel):
    """Everything the Leave home page needs for the caller."""

    policy: PolicyBrief
    leave_year: LeaveYear
    balances: list[Balance]
    optional_holidays: OptionalHolidayBalance
    wfh_auto_days_left_this_month: int | None
    approvers: list[PersonRef]
    # True when no active manager is set: requests go to HR.
    routes_to_hr: bool


class LeaveRequestCreate(BaseModel):
    """Request leave, WFH or an optional holiday."""

    kind: LeaveKind
    leave_type_id: uuid.UUID | None = None
    holiday_id: uuid.UUID | None = None
    start_date: date
    end_date: date
    half_day: HalfDay = HalfDay.NONE
    reason: str | None = Field(None, max_length=500)

    @model_validator(mode="after")
    def _shape(self) -> "LeaveRequestCreate":
        if self.end_date < self.start_date:
            raise ValueError("The end date must be on or after the start date.")
        if self.half_day != HalfDay.NONE and self.start_date != self.end_date:
            raise ValueError("A half day can only be requested for a single day.")
        if self.kind == LeaveKind.LEAVE and self.leave_type_id is None:
            raise ValueError("Choose a leave type.")
        if self.kind == LeaveKind.OPTIONAL_HOLIDAY and self.holiday_id is None:
            raise ValueError("Choose an optional holiday.")
        return self


class ExcludedDate(BaseModel):
    """A date inside the range that doesn't count, and why."""

    date: date
    reason: str


ProblemCode = Literal[
    "no_working_days",
    "insufficient_balance",
    "overlap",
    "crosses_leave_year",
    "too_far_back",
    "inactive_type",
    "holiday_not_optional",
    "optional_quota_used",
]


class LeaveProblem(BaseModel):
    """A reason the request can't be sent as it is."""

    code: ProblemCode
    message: str


class LeavePreview(BaseModel):
    """What a request would cost, before sending it."""

    days: Decimal
    excluded: list[ExcludedDate]
    balance_before: Decimal | None
    balance_after: Decimal | None
    auto_approved: bool
    approvers: list[PersonRef]
    routes_to_hr: bool
    problems: list[LeaveProblem]


class LeaveRequestRead(BaseModel):
    """A request as its requester, approvers and HR see it."""

    id: uuid.UUID
    user: PersonRef
    kind: LeaveKind
    leave_type: LeaveTypeBrief | None
    holiday_name: str | None
    start_date: date
    end_date: date
    half_day: HalfDay
    days: Decimal
    reason: str | None
    status: LeaveStatus
    approval_mode: ApprovalMode
    decided_by: PersonRef | None
    decided_at: datetime | None
    decision_note: str | None
    created_at: datetime
    can_cancel: bool


class AlsoOut(BaseModel):
    """A teammate who is out on one of the requested days (no type)."""

    name: str
    kind: LeaveKind
    start_date: date
    end_date: date


class ApprovalItem(BaseModel):
    """One request in the approvals queue."""

    request: LeaveRequestRead
    route: Literal["manager", "hr_queue", "hr_override"]
    designation: str | None
    department: str | None
    balance_after: Decimal | None
    also_out: list[AlsoOut]


class DecisionBody(BaseModel):
    """Approve or reject. A note is required to reject."""

    note: str | None = Field(None, max_length=500)


class ApprovalCount(BaseModel):
    """Pending requests the caller can act on (nav badge)."""

    pending: int
    # Whether the caller approves anything at all (shows the nav item).
    is_approver: bool


class CalendarEntry(BaseModel):
    """Someone out on the team calendar.

    ``leave_type`` and ``reason`` are set only for HR, the requester and
    their managers; everyone else sees "on leave".
    """

    request_id: uuid.UUID
    user: PersonRef
    kind: LeaveKind
    start_date: date
    end_date: date
    half_day: HalfDay
    status: LeaveStatus
    is_own: bool
    leave_type: LeaveTypeBrief | None
    reason: str | None


class CalendarRead(BaseModel):
    """Entries plus the caller's policy holidays for a date range."""

    entries: list[CalendarEntry]
    holidays: list[HolidayRead]
