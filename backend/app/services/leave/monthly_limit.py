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

"""Per-calendar-month limits (pure): the WFH allowance and a leave type's
monthly limit both ask "does any month go over?".

Each month stands alone: days not used in one month don't carry into the
next.
"""

from collections.abc import Mapping
from datetime import date
from decimal import Decimal

Month = tuple[int, int]

ZERO = Decimal("0")


def first_month_over(
    limit: Decimal,
    *,
    already: Mapping[Month, Decimal],
    requested: Mapping[Month, Decimal],
) -> Month | None:
    """The earliest month where booked plus requested days pass ``limit``, if any."""
    return next(
        (
            month
            for month, days in sorted(requested.items())
            if already.get(month, ZERO) + days > limit
        ),
        None,
    )


def _days(days: Decimal) -> str:
    value = f"{days.normalize():f}"
    return f"{value} day" if days == 1 else f"{value} days"


def limit_message(type_name: str, limit: Decimal, month: Month, booked: Decimal) -> str:
    """Why a request is refused, e.g. "Period leave is 1 day a month, and …"."""
    name = date(month[0], month[1], 1).strftime("%B")
    text = f"{type_name} is {_days(limit)} a month"
    if booked > ZERO:
        return f"{text}, and you already have {_days(booked)} booked in {name}."
    return f"{text}. Pick fewer days in {name}."
