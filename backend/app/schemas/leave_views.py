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

from pydantic import BaseModel, Field

from app.models.leave_request import HalfDay, LeaveKind, LeaveStatus
from app.schemas.leave import HolidayRead, LeaveRequestRead, LeaveTypeBrief, PersonRef


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
    # The requester's own working days, so a calendar doesn't hide someone
    # on another policy just because it's the viewer's day off.
    working_days: list[int]


class CalendarRead(BaseModel):
    """Entries plus the caller's policy holidays for a date range."""

    entries: list[CalendarEntry]
    holidays: list[HolidayRead]
