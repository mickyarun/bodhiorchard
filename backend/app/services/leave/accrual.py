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

"""How much of a year's allowance can be used by a given day (pure).

An upfront type gives the whole allocation at once. A monthly type gives an
equal part of it on the 1st of each month it covers, from the first month
the member counts on the policy to the leave year's last month: 18 days
over a full year is 1.5 a month, and a prorated 9 for someone who joined
in July is the same 1.5 a month over six months.

What can be booked from a day (:func:`usable_from`) is the smallest
headroom at any later month start, so leave booked ahead uses that
month's allowance, not an earlier one's, and the order people book in
never changes what is paid.
"""

from collections.abc import Sequence
from datetime import date
from decimal import ROUND_FLOOR, Decimal
from typing import NamedTuple

from app.models.leave_type import LeaveAccrual

TENTH = Decimal("0.1")
ZERO = Decimal("0")


class Booking(NamedTuple):
    """Paid days of one active leave request, by the day it starts."""

    start: date
    days: Decimal
    approved: bool


def earned_by(
    allocated: Decimal,
    accrual: LeaveAccrual,
    effective_from: date | None,
    year_start: date,
    year_end: date,
    on: date,
) -> Decimal:
    """Days of ``allocated`` released by ``on``.

    Args:
        allocated: The year's allocation (already prorated for a joiner).
        accrual: Whether it is given upfront or month by month.
        effective_from: When the member started counting on the policy;
            ``None`` means since before the year.
        year_start: First day of the leave year.
        year_end: Last day of the leave year.
        on: The day being asked about (a request's start, or today).

    Returns:
        Between 0 and ``allocated``, rounded down to the ledger's tenth of
        a day so nobody is credited early. The year's last month always
        releases exactly what is left.
    """
    if accrual == LeaveAccrual.UPFRONT or on >= year_end:
        return allocated
    first = max(year_start, effective_from) if effective_from else year_start
    if on < first.replace(day=1):
        return Decimal("0")
    months = _month_number(year_end) - _month_number(first) + 1
    credited = _month_number(on) - _month_number(first) + 1
    # Multiply before dividing so whole shares stay exact (18 x 10 / 12 = 15).
    return (allocated * credited / months).quantize(TENTH, rounding=ROUND_FLOOR)


def _month_number(day: date) -> int:
    """Months since year 0, so two dates subtract to a month count."""
    return day.year * 12 + day.month - 1


def usable_from(
    allocated: Decimal,
    accrual: LeaveAccrual,
    effective_from: date | None,
    year_start: date,
    year_end: date,
    on: date,
    adjustments: Decimal,
    bookings: Sequence[Booking],
) -> Decimal:
    """Days that can still be booked starting ``on`` without overdrawing any later month.

    The headroom at a day is what is earned by then, plus adjustments, less
    the paid days of leave starting by then. It is checked on ``on``, each
    later month start and the year's last day, and the smallest wins. For an
    upfront type that is always the year end: allocation + adjustments −
    everything booked.
    """
    checkpoints = [on, *_month_starts_after(on, year_end), year_end]
    return min(
        earned_by(allocated, accrual, effective_from, year_start, year_end, day)
        + adjustments
        - sum((b.days for b in bookings if b.start <= day), ZERO)
        for day in checkpoints
        if day >= on
    )


def taken_by(bookings: Sequence[Booking], on: date) -> Decimal:
    """Paid days of approved leave that has started by ``on``."""
    return sum((b.days for b in bookings if b.approved and b.start <= on), ZERO)


def _month_starts_after(on: date, year_end: date) -> list[date]:
    """The 1st of each month after ``on``'s, up to ``year_end``'s month."""
    starts: list[date] = []
    year, month = on.year, on.month
    while True:
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
        first = date(year, month, 1)
        if first > year_end:
            return starts
        starts.append(first)
