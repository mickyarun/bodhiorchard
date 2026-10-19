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

"""How many days of a leave type someone gets for a leave year (pure).

Someone who joins, or moves onto a policy, after the leave year starts
gets a prorated share of the quota, by days or by whole months as the
policy says, then rounded as the policy says. The result is written once
per member, type and year to the ledger, so the rule in force when it is
first written is the one that sticks for that year.
"""

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, Decimal

from app.models.leave_policy import AllocationRounding, ProrationMethod

HALF = Decimal("0.5")
WHOLE = Decimal("1")
TENTH = Decimal("0.1")

# Step and direction for each rounding choice.
_ROUNDING: dict[AllocationRounding, tuple[Decimal, str]] = {
    AllocationRounding.NONE: (TENTH, ROUND_HALF_UP),
    AllocationRounding.NEAREST_HALF: (HALF, ROUND_HALF_UP),
    AllocationRounding.UP_HALF: (HALF, ROUND_CEILING),
    AllocationRounding.DOWN_HALF: (HALF, ROUND_FLOOR),
    AllocationRounding.NEAREST_WHOLE: (WHOLE, ROUND_HALF_UP),
    AllocationRounding.UP_WHOLE: (WHOLE, ROUND_CEILING),
    AllocationRounding.DOWN_WHOLE: (WHOLE, ROUND_FLOOR),
}


@dataclass(frozen=True)
class ProrationRule:
    """A policy's proration settings."""

    method: ProrationMethod
    cutoff_day: int
    rounding: AllocationRounding


def allocation_for_year(
    quota: Decimal,
    effective_from: date | None,
    year_start: date,
    year_end: date,
    rule: ProrationRule,
) -> Decimal:
    """Days granted for one leave year.

    Args:
        quota: The leave type's yearly quota.
        effective_from: When the member started counting on this policy —
            the later of their joining date and the date they moved to the
            policy. ``None`` means "since before this year".
        year_start: First day of the leave year.
        year_end: Last day of the leave year.
        rule: The policy's proration method and rounding.

    Returns:
        Days granted: between 0 and ``quota``, at the ledger's one-decimal
        precision.
    """
    if effective_from is None or effective_from <= year_start:
        return quota
    if effective_from > year_end:
        return Decimal("0")
    if rule.method == ProrationMethod.NONE:
        return quota
    if rule.method == ProrationMethod.MONTHLY:
        part, whole = _months_counted(effective_from, year_end, rule.cutoff_day), 12
    else:
        part, whole = (year_end - effective_from).days + 1, (year_end - year_start).days + 1
    # Multiply before dividing so whole shares stay exact (12 x 6 / 12 = 6).
    return min(quota, round_days(quota * part / whole, rule.rounding))


def _months_counted(joined: date, year_end: date, cutoff_day: int) -> int:
    """Whole months from the joining month to the year's last month.

    The joining month counts only when they join on or before the cutoff.
    """
    months = (year_end.year - joined.year) * 12 + year_end.month - joined.month + 1
    return months if joined.day <= cutoff_day else months - 1


def round_days(days: Decimal, rounding: AllocationRounding) -> Decimal:
    """Round to the rule's step, e.g. up to the half day: 6.1 → 6.5."""
    step, direction = _ROUNDING[rounding]
    return ((days / step).quantize(WHOLE, rounding=direction) * step).quantize(TENTH)
