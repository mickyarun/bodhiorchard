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
"""

from datetime import date
from decimal import ROUND_FLOOR, Decimal

from app.models.leave_type import LeaveAccrual

TENTH = Decimal("0.1")


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
