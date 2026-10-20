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

"""How many of a request's days fall inside a report's date range.

A request wholly inside the range counts its stored ``days`` and
``lop_days`` as they are: approved leave that has started is never
re-priced, so recounting today could disagree with what was booked. Only a
request that crosses a range edge is recounted on the calendar it was
booked under, and any drift is pushed outside the range so the parts always
add up to the stored total. Loss of pay is the tail of a request (see
``cancellation``), so the range gets whatever unpaid days fall in it.
"""

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from app.models.leave_request import HalfDay
from app.services.leave.calendar_math import count_days

ZERO = Decimal("0")


@dataclass(frozen=True)
class Span:
    """A request as booked: its dates and stored day counts."""

    start: date
    end: date
    days: Decimal
    lop_days: Decimal


@dataclass(frozen=True)
class InRange:
    """The part of a request inside the range."""

    days: Decimal
    lop_days: Decimal


def overlaps(span: Span, start: date, end: date) -> bool:
    return span.start <= end and span.end >= start


def within(
    span: Span,
    start: date,
    end: date,
    *,
    working_days: Collection[int],
    holidays: Mapping[date, str],
) -> InRange:
    """``span``'s days and loss-of-pay days that fall in ``start..end``."""
    if not overlaps(span, start, end):
        return InRange(ZERO, ZERO)
    if start <= span.start and span.end <= end:
        return InRange(span.days, span.lop_days)

    def counted(first: date, last: date) -> Decimal:
        if first > last:
            return ZERO
        # Only multi-day requests cross an edge, and half days are single-day.
        found = count_days(first, last, HalfDay.NONE, working_days=working_days, holidays=holidays)
        return found.days

    before = min(counted(span.start, start - timedelta(days=1)), span.days)
    inside = min(counted(max(span.start, start), min(span.end, end)), span.days - before)
    after = span.days - before - inside
    lop = max(ZERO, min(inside, span.lop_days - after))
    return InRange(inside, lop)
