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

"""How many unused days carry into the next leave year, and when."""

from datetime import UTC, date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from app.models.leave_type import LeaveType
from app.schemas.leave_type import LeaveTypeWrite
from app.services.leave.balances import BalanceLine
from app.services.leave.calendar_math import leave_year_by_label
from app.services.leave.carry_rule import added_in, carry_days, carry_notes, due_year

D = Decimal


def line(
    cap: Decimal | None,
    *,
    allocated: Decimal | None = D(18),
    adjustments: Decimal = D(0),
    used: Decimal = D(0),
    pending: Decimal = D(0),
) -> BalanceLine:
    leave_type = LeaveType(name="Earned leave", code="EL", carry_forward_days=cap)
    return BalanceLine(
        leave_type=leave_type,
        allocated=allocated,
        earned=allocated,
        adjustments=adjustments,
        used=used,
        pending=pending,
        available=None,
        taken=used,
    )


def test_unused_up_to_the_cap_carries() -> None:
    assert carry_days(line(D(5), used=D(10))) == D(5)
    assert carry_days(line(D(5), used=D(15))) == D(3)


def test_adjustments_add_and_pending_leave_counts_as_spent() -> None:
    assert carry_days(line(D(10), adjustments=D(2), used=D(12), pending=D(5))) == D(3)


def test_half_days_carry_as_they_are() -> None:
    assert carry_days(line(D(5), used=D("15.5"))) == D("2.5")


def test_nothing_carries_without_a_cap() -> None:
    assert carry_days(line(None, used=D(2))) == D(0)
    assert carry_days(line(D(0), used=D(2))) == D(0)


def test_unlimited_or_overdrawn_carries_nothing() -> None:
    assert carry_days(line(D(5), allocated=None)) == D(0)
    assert carry_days(line(D(5), used=D(20))) == D(0)


@pytest.mark.parametrize(
    ("today", "start_month", "expected"),
    [
        (date(2027, 1, 1), 1, 2027),
        (date(2027, 1, 7), 1, 2027),
        (date(2027, 1, 8), 1, None),
        (date(2026, 12, 31), 1, None),
        (date(2027, 4, 3), 4, 2027),
        (date(2027, 1, 1), 4, None),
    ],
)
def test_due_in_the_first_week_of_the_leave_year(
    today: date, start_month: int, expected: int | None
) -> None:
    year = due_year(today, start_month)
    assert (year.label if year else None) == expected


def test_notes_name_both_years() -> None:
    assert carry_notes(leave_year_by_label(2026, 1), leave_year_by_label(2027, 1)) == (
        "Carried forward to 2027",
        "Carried forward from 2026",
    )
    assert carry_notes(leave_year_by_label(2026, 4), leave_year_by_label(2027, 4)) == (
        "Carried forward to 2027–28",
        "Carried forward from 2026–27",
    )


def test_a_type_set_up_in_the_new_year_has_nothing_to_carry() -> None:
    year = leave_year_by_label(2027, 1)
    kolkata = ZoneInfo("Asia/Kolkata")
    # 31 Dec 20:00 UTC is already 1 Jan in India.
    assert added_in(datetime(2026, 12, 31, 20, tzinfo=UTC), kolkata, year)
    assert not added_in(datetime(2026, 12, 31, 12, tzinfo=UTC), kolkata, year)


def cap_saved(quota: Decimal | None, cap: Decimal) -> Decimal | None:
    body = LeaveTypeWrite(
        name="Earned", code="el", annual_quota_days=quota, carry_forward_days=cap
    )
    return body.carry_forward_days


def test_the_setting_is_cleared_when_it_cannot_apply() -> None:
    assert cap_saved(D(18), D(5)) == D(5)
    assert cap_saved(D(18), D(0)) is None
    assert cap_saved(None, D(5)) is None
    with pytest.raises(ValueError, match="half days"):
        cap_saved(D(18), D("2.3"))
