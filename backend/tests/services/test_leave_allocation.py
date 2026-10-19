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

"""Prorating a new joiner's yearly allocation, by days or by months."""

from datetime import date
from decimal import Decimal

import pytest

from app.models.leave_policy import AllocationRounding as R
from app.models.leave_policy import ProrationMethod as M
from app.services.leave.allocation import ProrationRule, allocation_for_year, round_days

YEAR = (date(2026, 1, 1), date(2026, 12, 31))
APRIL_YEAR = (date(2026, 4, 1), date(2027, 3, 31))
DAILY = ProrationRule(M.DAILY, 15, R.NEAREST_HALF)
MONTHLY = ProrationRule(M.MONTHLY, 15, R.NEAREST_HALF)


def test_full_quota_for_people_who_started_before_the_year() -> None:
    assert allocation_for_year(Decimal("12"), date(2024, 3, 4), *YEAR, DAILY) == Decimal("12")
    assert allocation_for_year(Decimal("12"), None, *YEAR, MONTHLY) == Decimal("12")
    assert allocation_for_year(Decimal("12"), date(2026, 1, 1), *YEAR, DAILY) == Decimal("12")


def test_nothing_for_people_starting_after_the_year() -> None:
    assert allocation_for_year(Decimal("12"), date(2027, 2, 1), *YEAR, DAILY) == Decimal("0")


def test_no_proration_grants_the_full_quota() -> None:
    rule = ProrationRule(M.NONE, 15, R.NEAREST_HALF)
    assert allocation_for_year(Decimal("12"), date(2026, 11, 20), *YEAR, rule) == Decimal("12")


@pytest.mark.parametrize(
    ("rounding", "expected"),
    [
        # 1 Jul to 31 Dec is 184 of 365 days: 12 x 184 / 365 = 6.05.
        (R.NONE, "6.0"),
        (R.NEAREST_HALF, "6.0"),
        (R.UP_HALF, "6.5"),
        (R.DOWN_HALF, "6.0"),
        (R.NEAREST_WHOLE, "6"),
        (R.UP_WHOLE, "7"),
        (R.DOWN_WHOLE, "6"),
    ],
)
def test_daily_proration_with_each_rounding(rounding: R, expected: str) -> None:
    rule = ProrationRule(M.DAILY, 15, rounding)
    assert allocation_for_year(Decimal("12"), date(2026, 7, 1), *YEAR, rule) == Decimal(expected)


def test_monthly_counts_the_joining_month_up_to_the_cutoff() -> None:
    # Jul to Dec: 6 of 12 months.
    assert allocation_for_year(Decimal("12"), date(2026, 7, 15), *YEAR, MONTHLY) == Decimal("6")
    # Joined after the 15th: Aug to Dec, 5 months.
    assert allocation_for_year(Decimal("12"), date(2026, 7, 16), *YEAR, MONTHLY) == Decimal("5")


def test_monthly_cutoff_is_configurable() -> None:
    late = ProrationRule(M.MONTHLY, 25, R.NEAREST_HALF)
    assert allocation_for_year(Decimal("12"), date(2026, 7, 20), *YEAR, late) == Decimal("6")


@pytest.mark.parametrize(
    ("rounding", "expected"),
    [(R.NEAREST_WHOLE, "14"), (R.DOWN_WHOLE, "13"), (R.UP_HALF, "13.5")],
)
def test_monthly_share_is_rounded(rounding: R, expected: str) -> None:
    # Apr to Dec: 18 x 9 / 12 = 13.5.
    rule = ProrationRule(M.MONTHLY, 15, rounding)
    assert allocation_for_year(Decimal("18"), date(2026, 3, 20), *YEAR, rule) == Decimal(expected)


def test_leave_year_not_starting_in_january() -> None:
    joined = date(2027, 1, 5)
    # Jan to Mar: 3 of 12 months.
    assert allocation_for_year(Decimal("12"), joined, *APRIL_YEAR, MONTHLY) == Decimal("3")
    # 86 of 365 days: 2.83, to the nearest half.
    assert allocation_for_year(Decimal("12"), joined, *APRIL_YEAR, DAILY) == Decimal("3")


def test_rounding_up_never_grants_more_than_the_quota() -> None:
    rule = ProrationRule(M.DAILY, 15, R.UP_WHOLE)
    # 12.5 x 364 / 365 = 12.47, which rounds up to 13.
    assert allocation_for_year(Decimal("12.5"), date(2026, 1, 2), *YEAR, rule) == Decimal("12.5")


def test_round_days_keeps_one_decimal() -> None:
    assert round_days(Decimal("2.7397"), R.NONE) == Decimal("2.7")
    assert round_days(Decimal("6.25"), R.NEAREST_HALF) == Decimal("6.5")
    assert round_days(Decimal("6.24"), R.NEAREST_HALF) == Decimal("6.0")
