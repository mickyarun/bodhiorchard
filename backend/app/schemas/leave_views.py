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
"""DTOs for the approvals queue and the team calendar."""

import uuid
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.models.leave_request import HalfDay, LeaveKind, LeaveStatus
from app.schemas.leave import HolidayRead, LeaveRequestRead, LeaveTypeBrief, PersonRef
from app.schemas.leave_summary import Balance


class AlsoOut(BaseModel):
    """A teammate who is out on one of the requested days (no type)."""

    name: str
    kind: LeaveKind
    start_date: date
    end_date: date


class LastLeave(BaseModel):
    """The requester's most recent approved leave that has started."""

    leave_type: str | None
    start_date: date
    end_date: date
    days: Decimal


class ApprovalItem(BaseModel):
    """One request in the approvals queue.

    ``balances``, ``balance_year`` and ``last_leave`` are filled for pending
    requests only: they help decide, and are history once decided.
    """

    request: LeaveRequestRead
    route: Literal["manager", "hr_queue", "hr_override"]
    designation: str | None
    department: str | None
    balance_after: Decimal | None
    also_out: list[AlsoOut]
    balances: list[Balance] = []
    balance_year: int | None = None
    last_leave: LastLeave | None = None


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
    # The requester's own working days, so a calendar doesn't hide someone
    # on another policy just because it's the viewer's day off.
    working_days: list[int]


class CalendarRead(BaseModel):
    """Entries plus the caller's policy holidays for a date range."""

    entries: list[CalendarEntry]
    holidays: list[HolidayRead]


class ApprovalFilters(BaseModel):
    """Optional narrowing for the approvals queue; dates match overlapping leave."""

    start: date | None = None
    end: date | None = None
    kind: LeaveKind | None = None
    leave_type_id: uuid.UUID | None = None
    user_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _range(self) -> "ApprovalFilters":
        if self.start and self.end and self.end < self.start:
            raise ValueError("The end date must be on or after the start date.")
        return self

    @property
    def dated(self) -> bool:
        return self.start is not None or self.end is not None


class ApprovalQuery(ApprovalFilters):
    """The queue's query string: which tab, plus the filters."""

    status: Literal["pending", "decided"] = "pending"
