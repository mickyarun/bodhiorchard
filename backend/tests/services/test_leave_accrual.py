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
from app.services.leave.accrual import earned_by

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
