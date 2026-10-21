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

"""Leave report rows. Never a reason or a decision note: reports get exported."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel

from app.models.leave_request import ApprovalMode, HalfDay, LeaveKind, LeaveStatus
from app.schemas.leave import PersonRef


class NamedRef(BaseModel):
    """An id and a display name (leave type, office, policy)."""

    id: uuid.UUID
    name: str


class PersonColumns(BaseModel):
    """Who a row is about."""

    user_id: uuid.UUID
    name: str
    employee_code: str | None
    department: str | None
    office: str | None
    policy: str | None
    manager: str | None
    # Employee status (active / on notice / exited); None without a profile.
    status: str | None
    is_active: bool


class SummaryRow(PersonColumns):
    """Approved days taken in the range, plus what is still pending."""

    leave_by_type: dict[uuid.UUID, Decimal]
    # Days left per type in the leave year the range ends in, pending counted;
    # None = no limit. Types not on the member's policy are absent.
    left_by_type: dict[uuid.UUID, Decimal | None]
    leave_days: Decimal
    lop_days: Decimal
    wfh_days: Decimal
    optional_holidays: Decimal
    pending_days: Decimal


class SummaryReport(BaseModel):
    start: date
    end: date
    leave_types: list[NamedRef]
    rows: list[SummaryRow]


class RegisterRow(BaseModel):
    """One request."""

    request_id: uuid.UUID
    user_id: uuid.UUID
    name: str
    employee_code: str | None
    department: str | None
    kind: LeaveKind
    leave_type: str | None
    start_date: date
    end_date: date
    half_day: HalfDay
    days: Decimal
    lop_days: Decimal
    status: LeaveStatus
    approval_mode: ApprovalMode
    requested_at: datetime
    decided_by: str | None
    decided_at: datetime | None


class RegisterReport(BaseModel):
    rows: list[RegisterRow]
    # More matched than fit; narrow the dates or filters.
    truncated: bool


class BalanceRow(PersonColumns):
    """One member's numbers for one leave type. None = no limit."""

    leave_year: int
    leave_type_id: uuid.UUID
    leave_type: str
    allocated: Decimal | None
    adjustments: Decimal
    used: Decimal
    pending: Decimal
    available: Decimal | None
    lop_days: Decimal


class BalanceReport(BaseModel):
    rows: list[BalanceRow]


class ReportScopeRead(BaseModel):
    """What the viewer can report on, for the filter pickers."""

    all: bool
    people: list[PersonRef]
    departments: list[str]
    offices: list[NamedRef]
    policies: list[NamedRef]
    leave_types: list[NamedRef]
    current_leave_years: list[int]
