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

"""One member's ledger for one leave type and year, summed (pure)."""

from decimal import Decimal
from typing import NamedTuple

from app.models.leave_ledger import LedgerEntryType

ZERO = Decimal("0")
# Entries that make up a year's allocation (a correction re-states it).
_ALLOCATED = (LedgerEntryType.ALLOCATION, LedgerEntryType.CORRECTION)


class YearTotals(NamedTuple):
    """The year's allocation (None: not booked yet) and the days added and taken away.

    Added and taken-away days are kept apart, not netted: days added are
    usable straight away, days taken away only come off the year's total
    (:func:`app.services.leave.accrual.headroom_from`).
    """

    allocation: Decimal | None
    added: Decimal
    removed: Decimal

    @property
    def adjustments(self) -> Decimal:
        """Net days added (negative when more were taken away)."""
        return self.added + self.removed


NO_TOTALS = YearTotals(None, ZERO, ZERO)


def split_totals(sums: dict[LedgerEntryType, tuple[Decimal, Decimal]]) -> YearTotals:
    """A year's totals from its ``{entry type: (positive sum, negative sum)}``.

    A correction (HR recalculating a frozen allocation) is part of the
    allocation, so a monthly type releases it month by month like the rest;
    a manual adjustment is available at once.
    """
    others = [days for kind, days in sums.items() if kind not in _ALLOCATED]
    added = sum((plus for plus, _minus in others), ZERO)
    removed = sum((minus for _plus, minus in others), ZERO)
    correction = sum(sums.get(LedgerEntryType.CORRECTION, (ZERO, ZERO)), ZERO)
    if LedgerEntryType.ALLOCATION not in sums:
        # No allocation to correct; keep the days rather than drop them.
        return YearTotals(None, added + max(correction, ZERO), removed + min(correction, ZERO))
    allocation = sum(sums[LedgerEntryType.ALLOCATION], ZERO)
    return YearTotals(allocation + correction, added, removed)
