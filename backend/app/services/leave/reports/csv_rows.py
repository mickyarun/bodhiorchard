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

"""Each report's CSV layout: a header and one list of cells per row."""

import uuid
from collections.abc import Sequence
from decimal import Decimal

from app.models.leave_request import HalfDay
from app.schemas.leave_reports import (
    BalanceReport,
    PersonColumns,
    RegisterRow,
    SummaryReport,
    SummaryRow,
)
from app.services.leave.reports.csv_export import Cell

ZERO = Decimal("0")
PERSON_HEADER = ["Employee", "Code", "Department", "Office", "Policy", "Manager", "Status"]


def _person(row: PersonColumns) -> list[Cell]:
    status = row.status or ("active" if row.is_active else "inactive")
    return [
        row.name,
        row.employee_code,
        row.department,
        row.office,
        row.policy,
        row.manager,
        status,
    ]


def _taken_and_left(row: SummaryRow, type_id: uuid.UUID) -> tuple[Cell, Cell]:
    """Days taken in the range, and left in the year (blank if not on their policy)."""
    if type_id not in row.left_by_type:
        return row.leave_by_type.get(type_id), None
    left = row.left_by_type[type_id]
    return row.leave_by_type.get(type_id, ZERO), "No limit" if left is None else left


def summary_rows(report: SummaryReport) -> tuple[list[str], list[list[Cell]]]:
    header = [
        *PERSON_HEADER,
        *(f"{t.name} {part}" for t in report.leave_types for part in ("taken", "left")),
        "Leave days",
        "Loss of pay days",
        "WFH days",
        "Optional holidays",
        "Pending days",
    ]
    rows: list[list[Cell]] = [
        [
            *_person(r),
            *(cell for t in report.leave_types for cell in _taken_and_left(r, t.id)),
            r.leave_days,
            r.lop_days,
            r.wfh_days,
            r.optional_holidays,
            r.pending_days,
        ]
        for r in report.rows
    ]
    return header, rows


def register_rows(rows: Sequence[RegisterRow]) -> tuple[list[str], list[list[Cell]]]:
    header = [
        "Employee", "Code", "Department", "Kind", "Leave type", "From", "To", "Half day",
        "Days", "Loss of pay days", "Status", "Approval", "Requested at", "Decided by",
        "Decided at",
    ]  # fmt: skip
    return header, [
        [
            r.name,
            r.employee_code,
            r.department,
            r.kind.value,
            r.leave_type,
            r.start_date,
            r.end_date,
            None if r.half_day == HalfDay.NONE else r.half_day.value,
            r.days,
            r.lop_days,
            r.status.value,
            r.approval_mode.value,
            r.requested_at,
            r.decided_by,
            r.decided_at,
        ]
        for r in rows
    ]


def balance_rows(report: BalanceReport) -> tuple[list[str], list[list[Cell]]]:
    header = [
        *PERSON_HEADER,
        "Leave year", "Leave type", "Allocated", "Adjustments", "Used", "Pending",
        "Available", "Loss of pay days (year)",
    ]  # fmt: skip
    return header, [
        [
            *_person(r),
            r.leave_year,
            r.leave_type,
            "No limit" if r.allocated is None else r.allocated,
            r.adjustments,
            r.used,
            r.pending,
            "No limit" if r.available is None else r.available,
            r.lop_days,
        ]
        for r in report.rows
    ]
