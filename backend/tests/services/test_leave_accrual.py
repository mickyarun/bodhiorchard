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


"""Monthly accrual releases a year's allocation an equal part each month."""

from datetime import date
from decimal import Decimal

import pytest

from app.models.leave_type import LeaveAccrual
from app.services.leave.accrual import Booking, earned_by, taken_by, usable_from

YEAR_START, YEAR_END = date(2026, 1, 1), date(2026, 12, 31)
MONTHLY, UPFRONT = LeaveAccrual.MONTHLY, LeaveAccrual.UPFRONT


def earned(allocated: str, on: date, joined: date | None = None) -> Decimal:
    return earned_by(Decimal(allocated), MONTHLY, joined, YEAR_START, YEAR_END, on)


@pytest.mark.parametrize(
    ("on", "expected"),
    [
        (date(2026, 1, 1), "1.5"),  # credited on the 1st, not after the month
        (date(2026, 1, 31), "1.5"),
        (date(2026, 10, 1), "15"),
        (date(2026, 10, 21), "15"),
        (date(2026, 12, 1), "18"),
    ],
)
def test_eighteen_a_year_is_one_and_a_half_a_month(on: date, expected: str) -> None:
    assert earned("18", on) == Decimal(expected)


def test_upfront_and_past_years_give_everything() -> None:
    assert earned_by(Decimal(18), UPFRONT, None, YEAR_START, YEAR_END, date(2026, 1, 1)) == 18
    assert earned("18", date(2027, 3, 1)) == 18


def test_a_joiner_earns_their_prorated_share_over_the_months_left() -> None:
    # Joined 15 July: 9 days prorated over July to December is 1.5 a month,
    # and July itself is credited on their first day.
    joined = date(2026, 7, 15)
    assert earned("9", date(2026, 6, 30), joined) == 0
    assert earned("9", date(2026, 7, 15), joined) == Decimal("1.5")
    assert earned("9", date(2026, 9, 10), joined) == Decimal("4.5")
    assert earned("9", date(2026, 12, 31), joined) == 9


def test_uneven_shares_round_down_and_the_last_month_settles_up() -> None:
    # 4 a year: 0.333… a month is never credited early, and December
    # releases whatever is left so the year adds up to exactly 4.
    assert earned("4", date(2026, 1, 5)) == Decimal("0.3")
    assert earned("4", date(2026, 6, 5)) == Decimal("2")
    assert earned("4", date(2026, 11, 5)) == Decimal("3.6")
    assert earned("4", date(2026, 12, 5)) == 4


def booked(*items: tuple[date, str, bool]) -> list[Booking]:
    return [Booking(start=d, days=Decimal(days), approved=ok) for d, days, ok in items]


def usable(on: date, bookings: list[Booking], accrual: LeaveAccrual = MONTHLY) -> Decimal:
    return usable_from(Decimal(18), accrual, None, YEAR_START, YEAR_END, on, Decimal(0), bookings)


def test_leave_booked_ahead_uses_its_own_months_allowance() -> None:
    # 10 days in December are covered by December's 18 earned, so a
    # February request still has February's 3 days: booking order is moot.
    december = booked((date(2026, 12, 7), "10", True))
    assert usable(date(2026, 2, 9), december) == Decimal("3")
    # But nothing earlier may eat into what December needs: by March only
    # 4.5 is earned, and the year can spare 18 - 10 = 8 at most.
    assert usable(date(2026, 3, 2), december) == Decimal("4.5")
    assert usable(date(2026, 8, 3), december) == Decimal("8")


def test_upfront_is_the_whole_year_less_everything_booked() -> None:
    bookings = booked((date(2026, 12, 7), "10", True), (date(2026, 2, 9), "3", False))
    assert usable(date(2026, 2, 1), bookings, UPFRONT) == Decimal("5")


def test_taken_counts_only_approved_leave_that_has_started() -> None:
    bookings = booked(
        (date(2026, 3, 2), "2", True),
        (date(2026, 3, 9), "1", False),
        (date(2026, 12, 7), "10", True),
    )
    assert taken_by(bookings, date(2026, 10, 21)) == Decimal("2")


@pytest.mark.parametrize("late_first", [True, False])
def test_two_bookings_in_one_month_share_that_months_allowance(late_first: bool) -> None:
    # By February 3 days are earned. 3 days on the 20th and 1 on the 10th
    # need 4: whichever is booked second gets only what is left.
    late, early = (date(2026, 2, 20), "3"), (date(2026, 2, 10), "1")
    first, second = (late, early) if late_first else (early, late)
    paid_first = min(Decimal(first[1]), usable(first[0], []))
    after_first = booked((first[0], str(paid_first), True))
    paid_second = min(Decimal(second[1]), usable(second[0], after_first))
    assert paid_first + paid_second == 3


def test_leave_on_the_1st_counts_that_months_share() -> None:
    assert usable(date(2026, 3, 1), []) == Decimal("4.5")
    assert usable(date(2026, 3, 1), booked((date(2026, 3, 1), "4.5", False))) == 0
