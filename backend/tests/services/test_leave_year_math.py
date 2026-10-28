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

"""Leave-year edges in the pure date maths: leap days and years not starting in January."""

from datetime import date
from decimal import Decimal

import pytest

from app.models.leave_policy import AllocationRounding, ProrationMethod
from app.models.leave_request import HalfDay
from app.models.leave_type import LeaveAccrual
from app.services.leave.accrual import earned_by
from app.services.leave.allocation import ProrationRule, allocation_for_year
from app.services.leave.calendar_math import (
    count_days,
    days_by_month,
    leave_year_bounds,
    leave_year_by_label,
    same_leave_year,
)
from app.services.leave.date_rules import date_problems

D = Decimal
WEEK = [0, 1, 2, 3, 4]
LEAP = date(2028, 2, 29)
DAILY = ProrationRule(ProrationMethod.DAILY, 15, AllocationRounding.NONE)


@pytest.mark.parametrize(
    ("start_month", "label", "start", "end"),
    [
        (1, 2028, date(2028, 1, 1), date(2028, 12, 31)),
        (2, 2028, date(2028, 2, 1), date(2029, 1, 31)),
        # A March year that starts in 2027 ends on the leap day.
        (3, 2027, date(2027, 3, 1), LEAP),
        (4, 2027, date(2027, 4, 1), date(2028, 3, 31)),
    ],
)
def test_the_leap_day_belongs_to_one_leave_year(
    start_month: int, label: int, start: date, end: date
) -> None:
    bounds = leave_year_bounds(LEAP, start_month)
    assert (bounds.label, bounds.start, bounds.end) == (label, start, end)
    assert leave_year_by_label(label, start_month) == bounds


def test_a_march_year_after_a_leap_year_ends_on_feb_28() -> None:
    assert leave_year_by_label(2028, 3).end == date(2029, 2, 28)


def test_the_leap_day_counts_as_a_working_day_and_falls_in_february() -> None:
    counted = count_days(
        date(2028, 2, 28), date(2028, 3, 1), HalfDay.NONE, working_days=WEEK, holidays={}
    )
    assert (counted.days, counted.excluded) == (D(3), [])
    split = days_by_month(
        date(2028, 2, 28), date(2028, 3, 1), HalfDay.NONE, working_days=WEEK, holidays={}
    )
    assert split == {(2028, 2): D(2), (2028, 3): D(1)}
    morning = count_days(
        LEAP, LEAP, HalfDay.FIRST_HALF, working_days=WEEK, holidays={LEAP: "Leap"}
    )
    assert (morning.days, morning.excluded) == (D(0), [(LEAP, "Leap")])


def test_daily_proration_divides_by_366_in_a_leap_year() -> None:
    year = (date(2028, 1, 1), date(2028, 12, 31))
    # 1 Jul to 31 Dec is 184 of 366 days: 12 x 184 / 366 = 6.03 -> 6.0.
    assert allocation_for_year(D(12), date(2028, 7, 1), *year, DAILY) == D("6.0")
    # Joining on the leap day: 307 of 366 days, 10.07 -> 10.1.
    assert allocation_for_year(D(12), LEAP, *year, DAILY) == D("10.1")
    # Joining on the last day still earns that one day's share.
    assert allocation_for_year(D(366), year[1], *year, DAILY) == D("1.0")


def test_monthly_accrual_on_the_leap_day_has_february_share() -> None:
    year = (date(2028, 1, 1), date(2028, 12, 31))
    assert earned_by(D(12), LeaveAccrual.MONTHLY, None, *year, LEAP) == D(2)
    # An April year: the leap day sits in its 11th month.
    april = (date(2027, 4, 1), date(2028, 3, 31))
    assert earned_by(D(12), LeaveAccrual.MONTHLY, None, *april, LEAP) == D(11)


@pytest.mark.parametrize(
    ("start", "end", "start_month", "same"),
    [
        (date(2030, 12, 31), date(2031, 1, 1), 1, False),
        (date(2030, 12, 31), date(2031, 1, 1), 4, True),
        (date(2030, 3, 31), date(2030, 4, 1), 4, False),
        (date(2030, 3, 31), date(2030, 4, 1), 1, True),
        (date(2030, 1, 1), date(2030, 12, 31), 1, True),
    ],
)
def test_same_leave_year_at_each_boundary(
    start: date, end: date, start_month: int, same: bool
) -> None:
    assert same_leave_year(start, end, start_month) is same


def test_date_rules_name_the_split_day_and_the_last_bookable_day() -> None:
    today = date(2030, 12, 16)
    across = date_problems(
        date(2030, 12, 31),
        date(2031, 1, 1),
        today=today,
        backdate_limit_days=7,
        year_start_month=1,
    )
    assert across == [
        ("crosses_leave_year", "Requests can't span two leave years. Split it at Tue 31 Dec.")
    ]
    last = date(2031, 12, 31)
    assert date_problems(last, last, today=today, backdate_limit_days=7, year_start_month=1) == []
    # Backdating stops exactly at the limit.
    limit = date(2030, 12, 9)
    assert (
        date_problems(limit, limit, today=today, backdate_limit_days=7, year_start_month=1) == []
    )
    early = date(2030, 12, 8)
    codes = [
        code
        for code, _ in date_problems(
            early, early, today=today, backdate_limit_days=7, year_start_month=1
        )
    ]
    assert codes == ["too_far_back"]
