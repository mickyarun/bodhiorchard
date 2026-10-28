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

"""One balance, never below zero: ledger totals, headroom and the paid split around zero."""

from datetime import date
from decimal import Decimal

import pytest

from app.models.leave_ledger import LedgerEntryType as E
from app.models.leave_type import LeaveAccrual
from app.repositories.leave_ledger_totals import NO_TOTALS, YearTotals, split_totals
from app.services.leave.accrual import Booking, headroom_from, usable_from
from app.services.leave.loss_of_pay import split_paid

D = Decimal
START, END = date(2030, 1, 1), date(2030, 12, 31)
MONTHLY, UPFRONT = LeaveAccrual.MONTHLY, LeaveAccrual.UPFRONT


@pytest.mark.parametrize(
    ("sums", "expected"),
    [
        ({}, NO_TOTALS),
        ({E.ALLOCATION: (D(12), D(0))}, YearTotals(D(12), D(0), D(0))),
        # A correction re-states the allocation, either way.
        (
            {E.ALLOCATION: (D(12), D(0)), E.CORRECTION: (D(0), D(-2))},
            YearTotals(D(10), D(0), D(0)),
        ),
        # Added and taken-away days are kept apart, never netted.
        (
            {E.ALLOCATION: (D(12), D(0)), E.ADJUSTMENT: (D(5), D(-3))},
            YearTotals(D(12), D(5), D(-3)),
        ),
        # Days carried in are added; a carry out is taken away.
        (
            {E.ALLOCATION: (D(12), D(0)), E.CARRY_FORWARD: (D(2), D(-1))},
            YearTotals(D(12), D(2), D(-1)),
        ),
        # No allocation yet: a correction is kept by its net sign.
        ({E.CORRECTION: (D(3), D(-1))}, YearTotals(None, D(2), D(0))),
        ({E.CORRECTION: (D(1), D(-3))}, YearTotals(None, D(0), D(-2))),
    ],
)
def test_split_totals(sums: dict[E, tuple[Decimal, Decimal]], expected: YearTotals) -> None:
    assert split_totals(sums) == expected


def test_adjustments_are_the_net_of_added_and_taken_away() -> None:
    assert YearTotals(D(12), D(5), D(-7)).adjustments == D(-2)
    assert NO_TOTALS.adjustments == 0


def _booked(*items: tuple[date, str]) -> list[Booking]:
    return [Booking(start=d, days=D(days), approved=True) for d, days in items]


def _room(
    on: date,
    bookings: list[Booking],
    *,
    accrual: LeaveAccrual = UPFRONT,
    added: str = "0",
    removed: str = "0",
) -> tuple[Decimal, Decimal]:
    """``(headroom, usable)`` for 12 a year."""
    args = (D(12), accrual, None, START, END, on, D(added), D(removed), bookings)
    return headroom_from(*args), usable_from(*args)


def test_booking_exactly_the_balance_leaves_zero() -> None:
    assert _room(START, _booked((date(2030, 6, 3), "12"))) == (D(0), D(0))


def test_overbooked_headroom_is_negative_but_usable_stops_at_zero() -> None:
    assert _room(START, _booked((date(2030, 6, 3), "13"))) == (D(-1), D(0))
    assert _room(START, _booked((date(2030, 6, 3), "12")), removed="-0.5") == (
        D("-0.5"),
        D(0),
    )


def test_days_taken_away_only_count_against_the_year_end() -> None:
    # One day of January leave against January's single earned day: a
    # deduction of 2 doesn't make January short, the year still has 9 spare.
    january = _booked((date(2030, 1, 7), "1"))
    assert _room(START, january, accrual=MONTHLY, removed="-2") == (D(0), D(0))
    assert _room(date(2030, 12, 1), january, accrual=MONTHLY, removed="-2") == (D(9), D(9))


def test_days_added_are_usable_straight_away() -> None:
    assert _room(START, [], accrual=MONTHLY, added="5") == (D(6), D(6))
    # A deduction bigger than the grant still can't push January below zero.
    assert _room(START, [], accrual=MONTHLY, added="5", removed="-20")[1] == 0


@pytest.mark.parametrize(
    ("days", "available", "expected"),
    [
        ("1", "0", ("0", "1")),
        ("1", "0.5", ("0.5", "0.5")),
        ("0.5", "0.5", ("0.5", "0")),
        ("0.5", "-3", ("0", "0.5")),
        ("2", "2", ("2", "0")),
    ],
)
def test_split_paid_around_zero(days: str, available: str, expected: tuple[str, str]) -> None:
    assert split_paid(D(days), D(available)) == (D(expected[0]), D(expected[1]))
