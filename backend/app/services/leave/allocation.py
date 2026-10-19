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

The result is written once per member, type and year to the ledger, so
whatever rule lives here is frozen for that year when first read.
"""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal


def allocation_for_year(
    quota: Decimal,
    effective_from: date | None,
    year_start: date,
    year_end: date,
) -> Decimal:
    """Days granted for one leave year.

    Args:
        quota: The leave type's yearly quota.
        effective_from: When the member started counting on this policy —
            the later of their joining date and the date they moved to the
            policy. ``None`` means "since before this year".
        year_start: First day of the leave year.
        year_end: Last day of the leave year.

    Returns:
        Days granted, never negative, in steps of 0.5.
    """
    if effective_from is None or effective_from <= year_start:
        return quota
    if effective_from > year_end:
        return Decimal("0")
    # Joined (or moved policy) part-way through the year.
    # TODO(you): HR's proration rule. See the note in the conversation.
    raise NotImplementedError("Mid-year proration rule not decided yet")


def round_to_half(days: Decimal) -> Decimal:
    """Round to the nearest 0.5 day (half up), e.g. 6.24 → 6.0, 6.25 → 6.5."""
    return (days * 2).quantize(Decimal("1"), rounding=ROUND_HALF_UP) / 2
