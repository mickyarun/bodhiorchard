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


class PersonRef(BaseModel):
    """A member by id and name."""

    user_id: uuid.UUID
    name: str


# A request can't cross a leave year, so nothing valid is longer than this.
# Checked up front so a huge range never reaches the day-by-day counting.
MAX_REQUEST_SPAN_DAYS = 366


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
        if (self.end_date - self.start_date).days >= MAX_REQUEST_SPAN_DAYS:
            raise ValueError("A request can cover at most one leave year.")
        if self.half_day != HalfDay.NONE and self.start_date != self.end_date:
            raise ValueError("A half day can only be requested for a single day.")
        if self.kind == LeaveKind.LEAVE and self.leave_type_id is None:
            raise ValueError("Choose a leave type.")
        if self.kind == LeaveKind.OPTIONAL_HOLIDAY and self.holiday_id is None:
            raise ValueError("Choose an optional holiday.")
        # Fields that don't apply to the kind are dropped, so a WFH request
        # can't carry (and be labelled with) an arbitrary leave type.
        if self.kind != LeaveKind.LEAVE:
            self.leave_type_id = None
        if self.kind != LeaveKind.OPTIONAL_HOLIDAY:
            self.holiday_id = None
        else:
            self.half_day = HalfDay.NONE
        return self


class ExcludedDate(BaseModel):
    """A date inside the range that doesn't count, and why."""

    date: date
    reason: str


ProblemCode = Literal[
    "no_working_days",
    "overlap",
    "crosses_leave_year",
    "too_far_back",
    "inactive_type",
    "holiday_not_optional",
    "optional_quota_used",
    "too_far_ahead",
    "no_approver",
    "remote_no_wfh",
]


class LeaveProblem(BaseModel):
    """A reason the request can't be sent as it is."""

    code: ProblemCode
    message: str


class LeavePreview(BaseModel):
    """What a request would cost, before sending it."""

    days: Decimal
    # Of ``days``, those past the balance: taken as loss of pay.
    lop_days: Decimal
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
    lop_days: Decimal
    reason: str | None
    status: LeaveStatus
    approval_mode: ApprovalMode
    decided_by: PersonRef | None
    decided_at: datetime | None
    decision_note: str | None
    created_at: datetime
    can_cancel: bool
