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

"""Who can use a leave type, and the per-month limit."""

from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.models.employee_profile import Gender
from app.services.leave.eligibility import can_use, usable_types
from app.services.leave.monthly_limit import first_month_over, limit_message

D = Decimal
WOMEN = SimpleNamespace(eligible_genders=[Gender.FEMALE])
EVERYONE = SimpleNamespace(eligible_genders=None)


@pytest.mark.parametrize(
    ("gender", "allowed"),
    [
        (Gender.FEMALE, True),
        (Gender.MALE, False),
        (Gender.NON_BINARY, False),
        (Gender.PREFER_NOT_TO_SAY, False),
        (None, False),
    ],
)
def test_women_only_needs_female_on_the_profile(gender: Gender | None, allowed: bool) -> None:
    profile = SimpleNamespace(gender=gender)
    assert can_use(WOMEN, profile) is allowed  # type: ignore[arg-type]
    assert can_use(EVERYONE, profile) is True  # type: ignore[arg-type]


def test_women_only_is_hidden_without_a_profile() -> None:
    assert can_use(WOMEN, None) is False  # type: ignore[arg-type]
    assert usable_types([EVERYONE, WOMEN], None) == [EVERYONE]  # type: ignore[list-item]


def test_first_month_over_the_limit() -> None:
    oct_, nov = (2026, 10), (2026, 11)
    assert first_month_over(D(1), already={}, requested={oct_: D(1)}) is None
    assert first_month_over(D(1), already={oct_: D(1)}, requested={oct_: D("0.5")}) == oct_
    # Each month stands alone: October's unused day doesn't help November.
    assert first_month_over(D(1), already={}, requested={oct_: D(1), nov: D(2)}) == nov
    assert first_month_over(D(1), already={nov: D(1)}, requested={oct_: D(1)}) is None


def test_limit_message() -> None:
    assert (
        limit_message("Period leave", D(1), (2026, 10), D(1))
        == "Period leave is 1 day a month, and you already have 1 day booked in October."
    )
    assert (
        limit_message("Period leave", D(1), (2026, 10), D(0))
        == "Period leave is 1 day a month. Pick fewer days in October."
    )


def test_a_type_can_cover_several_genders() -> None:
    both = SimpleNamespace(eligible_genders=[Gender.FEMALE, Gender.NON_BINARY])
    assert can_use(both, SimpleNamespace(gender=Gender.NON_BINARY)) is True  # type: ignore[arg-type]
    assert can_use(both, SimpleNamespace(gender=Gender.MALE)) is False  # type: ignore[arg-type]
