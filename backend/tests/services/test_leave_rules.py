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

"""Pure leave rules: leave years, day counting, WFH allowance."""

from datetime import date
from decimal import Decimal

import pytest

from app.models.leave_policy import WfhApproval
from app.models.leave_request import HalfDay
from app.services.leave.calendar_math import (
    count_days,
    days_by_month,
    leave_year_bounds,
    same_leave_year,
)
from app.services.leave.loss_of_pay import split_paid
from app.services.leave.wfh_policy import auto_days_left, needs_approval

MON_FRI = {0, 1, 2, 3, 4}
DIWALI = {date(2026, 10, 21): "Diwali"}  # a Wednesday


def test_calendar_leave_year() -> None:
    year = leave_year_bounds(date(2026, 10, 19), 1)
    assert (year.label, year.start, year.end) == (2026, date(2026, 1, 1), date(2026, 12, 31))


def test_april_leave_year_before_and_after_start() -> None:
    assert leave_year_bounds(date(2027, 3, 31), 4).label == 2026
    assert leave_year_bounds(date(2027, 4, 1), 4).label == 2027
    assert leave_year_bounds(date(2026, 10, 1), 4).end == date(2027, 3, 31)


def test_range_across_a_leave_year_boundary() -> None:
    assert not same_leave_year(date(2026, 12, 31), date(2027, 1, 1), 1)
    assert same_leave_year(date(2026, 12, 31), date(2027, 1, 1), 4)


def test_counts_working_days_and_explains_exclusions() -> None:
    # Mon 19 – Sun 25 Oct: Wed is Diwali, Sat/Sun are weekends.
    result = count_days(
        date(2026, 10, 19), date(2026, 10, 25), HalfDay.NONE, working_days=MON_FRI, holidays=DIWALI
    )
    assert result.days == Decimal("4")
    assert [reason for _, reason in result.excluded] == ["Diwali", "Sat", "Sun"]


def test_half_day_counts_half() -> None:
    result = count_days(
        date(2026, 10, 20),
        date(2026, 10, 20),
        HalfDay.SECOND_HALF,
        working_days=MON_FRI,
        holidays={},
    )
    assert result.days == Decimal("0.5")


def test_half_day_on_a_holiday_counts_nothing() -> None:
    result = count_days(
        date(2026, 10, 21),
        date(2026, 10, 21),
        HalfDay.FIRST_HALF,
        working_days=MON_FRI,
        holidays=DIWALI,
    )
    assert result.days == Decimal("0")


def test_six_day_week() -> None:
    result = count_days(
        date(2026, 10, 19),
        date(2026, 10, 25),
        HalfDay.NONE,
        working_days=MON_FRI | {5},
        holidays={},
    )
    assert result.days == Decimal("6")


def test_days_split_across_months() -> None:
    by_month = days_by_month(
        date(2026, 10, 29), date(2026, 11, 3), HalfDay.NONE, working_days=MON_FRI, holidays={}
    )
    assert by_month == {(2026, 10): Decimal("2"), (2026, 11): Decimal("2")}


@pytest.mark.parametrize(
    ("already", "requested", "expected"),
    [
        ({}, {(2026, 10): Decimal("3")}, False),
        ({(2026, 10): Decimal("2")}, {(2026, 10): Decimal("1")}, False),
        ({(2026, 10): Decimal("2")}, {(2026, 10): Decimal("2")}, True),
        # Within allowance in October, over it in November → manager approves.
        ({(2026, 11): Decimal("3")}, {(2026, 10): Decimal("1"), (2026, 11): Decimal("1")}, True),
        ({(2026, 10): Decimal("2.5")}, {(2026, 10): Decimal("0.5")}, False),
    ],
)
def test_wfh_allowance(
    already: dict[tuple[int, int], Decimal],
    requested: dict[tuple[int, int], Decimal],
    expected: bool,
) -> None:
    assert (
        needs_approval(WfhApproval.AUTO_WITHIN_ALLOWANCE, 3, already=already, requested=requested)
        is expected
    )


def test_wfh_modes() -> None:
    big = {(2026, 10): Decimal("20")}
    assert needs_approval(WfhApproval.AUTO, 0, already={}, requested=big) is False
    assert needs_approval(WfhApproval.REQUIRED, 99, already={}, requested=big) is True


def test_auto_days_left() -> None:
    assert auto_days_left(WfhApproval.AUTO_WITHIN_ALLOWANCE, 3, Decimal("1")) == 2
    assert auto_days_left(WfhApproval.AUTO_WITHIN_ALLOWANCE, 3, Decimal("5")) == 0
    assert auto_days_left(WfhApproval.REQUIRED, 3, Decimal("0")) is None


def test_split_paid_covers_what_the_balance_can() -> None:
    assert split_paid(Decimal("3"), Decimal("5")) == (Decimal("3"), Decimal("0"))
    assert split_paid(Decimal("3"), Decimal("1.5")) == (Decimal("1.5"), Decimal("1.5"))
    assert split_paid(Decimal("2"), Decimal("-1")) == (Decimal("0"), Decimal("2"))
    assert split_paid(Decimal("4"), None) == (Decimal("4"), Decimal("0"))
