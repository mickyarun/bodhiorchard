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

"""The streak multiplier table and the milestone SP values it pairs with."""

from __future__ import annotations

import pytest

from app.services.sp_rules import SP_STREAK_14, SP_STREAK_30
from app.services.xp_rules import streak_multiplier


@pytest.mark.parametrize(
    ("days", "multiplier"),
    [
        (0, 1.0),
        (1, 1.0),
        (6, 1.0),
        (7, 1.5),
        (13, 1.5),
        (14, 2.0),
        (29, 2.0),
        (30, 2.5),
        (400, 2.5),
    ],
)
def test_each_tier_starts_on_its_day_and_holds_until_the_next(
    days: int, multiplier: float
) -> None:
    assert streak_multiplier(days) == multiplier


def test_streak_milestones_are_scarce_and_the_longer_one_pays_more() -> None:
    """SP is a scarce currency: a month of daily activity is worth one SP, not thirty."""
    assert 0 < SP_STREAK_14 < SP_STREAK_30 <= 1.0
