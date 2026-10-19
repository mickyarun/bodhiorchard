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

"""Pure date arithmetic for leave: leave years and working-day counts.

No I/O. Weekdays are 0 = Monday … 6 = Sunday, as in ``date.weekday()``.
Only *mandatory* holidays are passed in: an optional holiday is a normal
working day unless someone takes it.
"""

from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from app.models.leave_request import HalfDay

FULL_DAY = Decimal("1")
HALF_DAY = Decimal("0.5")
_WEEKDAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


@dataclass(frozen=True)
class LeaveYearBounds:
    """A leave year; ``label`` is the calendar year it starts in."""

    label: int
    start: date
    end: date


@dataclass(frozen=True)
class DayCount:
    """Days a range uses, and the dates inside it that don't count."""

    days: Decimal
    excluded: list[tuple[date, str]] = field(default_factory=list)


def leave_year_bounds(on: date, start_month: int) -> LeaveYearBounds:
    """The leave year containing ``on`` when years start in ``start_month``."""
    label = on.year if on.month >= start_month else on.year - 1
    return leave_year_by_label(label, start_month)


def leave_year_by_label(label: int, start_month: int) -> LeaveYearBounds:
    """The leave year starting in ``start_month`` of ``label``."""
    start = date(label, start_month, 1)
    next_start = date(label + 1, start_month, 1)
    return LeaveYearBounds(label=label, start=start, end=next_start - timedelta(days=1))


def same_leave_year(start: date, end: date, start_month: int) -> bool:
    """True if both dates fall in one leave year."""
    return leave_year_bounds(start, start_month) == leave_year_bounds(end, start_month)


def iter_dates(start: date, end: date) -> list[date]:
    """Every date from ``start`` to ``end`` inclusive."""
    return [start + timedelta(days=offset) for offset in range((end - start).days + 1)]


def count_days(
    start: date,
    end: date,
    half_day: HalfDay,
    *,
    working_days: Collection[int],
    holidays: Mapping[date, str],
) -> DayCount:
    """Working days in ``start..end``, skipping weekends and mandatory holidays.

    A half day applies only to a single-day range and counts 0.5 if that
    day is itself a working day.
    """
    counted = Decimal("0")
    excluded: list[tuple[date, str]] = []
    for day in iter_dates(start, end):
        if day.weekday() not in working_days:
            excluded.append((day, _WEEKDAY_NAMES[day.weekday()]))
        elif day in holidays:
            excluded.append((day, holidays[day]))
        else:
            counted += FULL_DAY
    if half_day != HalfDay.NONE and start == end and counted:
        counted = HALF_DAY
    return DayCount(days=counted, excluded=excluded)


def days_by_month(
    start: date,
    end: date,
    half_day: HalfDay,
    *,
    working_days: Collection[int],
    holidays: Mapping[date, str],
) -> dict[tuple[int, int], Decimal]:
    """Working days in the range, split by ``(year, month)``."""
    out: dict[tuple[int, int], Decimal] = {}
    for day in iter_dates(start, end):
        if day.weekday() in working_days and day not in holidays:
            key = (day.year, day.month)
            out[key] = out.get(key, Decimal("0")) + FULL_DAY
    if half_day != HalfDay.NONE and start == end and out:
        out = {key: HALF_DAY for key in out}
    return out
