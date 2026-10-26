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

"""How many unused days carry into the next leave year, and when (pure).

Unused is the old year's whole allocation (a monthly type counts all twelve
months) plus adjustments, minus approved and pending paid days; loss-of-pay
days never came out of the balance. Up to the type's cap carries over and
the rest lapses. Carried days last the whole new year.

The days move: a credit in the new year and a matching debit in the old one,
so leave backdated into the old year can't spend them a second time.
"""

from datetime import date, datetime, timedelta, tzinfo
from decimal import Decimal

from app.services.leave.balances import BalanceLine
from app.services.leave.calendar_math import LeaveYearBounds, leave_year_bounds

ZERO = Decimal("0")
# Carrying runs on the first day of the leave year; a server that was down
# then catches up on a later day of this first week.
CATCH_UP = timedelta(days=7)


def carry_days(line: BalanceLine) -> Decimal:
    """Days of ``line``'s year that carry into the next one (0 if none)."""
    cap = line.leave_type.carry_forward_days
    if not cap or line.allocated is None:
        return ZERO
    unused = line.allocated + line.adjustments - line.used - line.pending
    return min(max(unused, ZERO), cap)


def due_year(today: date, start_month: int) -> LeaveYearBounds | None:
    """The leave year to carry into, while ``today`` is in its first week."""
    year = leave_year_bounds(today, start_month)
    return year if today < year.start + CATCH_UP else None


def added_in(created_at: datetime, zone: tzinfo, year: LeaveYearBounds) -> bool:
    """True if a type was set up on or after ``year`` began: it has no last year to carry."""
    return created_at.astimezone(zone).date() >= year.start


def year_span(year: LeaveYearBounds) -> str:
    """A leave year as people say it: 2026, or 2026–27 when it spans two."""
    label = year.label
    return str(label) if year.start.month == 1 else f"{label}–{str(label + 1)[-2:]}"


def carry_notes(old_year: LeaveYearBounds, new_year: LeaveYearBounds) -> tuple[str, str]:
    """Ledger notes for the days leaving the old year and arriving in the new one."""
    return (
        f"Carried forward to {year_span(new_year)}",
        f"Carried forward from {year_span(old_year)}",
    )
