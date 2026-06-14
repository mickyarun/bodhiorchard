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

"""Quiz scoring formula — pure, tunable constants + helpers.

Accuracy dominates: a correct answer is worth ``BASE_POINTS``; on top of that a
speed bonus of up to ``MAX_SPEED_BONUS`` decays linearly to zero over the
``speed_grace`` window, so answering early helps but never beats correctness, and
the window stays genuinely open (no advantage to a 9am refresh race once grace
has passed). A wrong answer scores zero.
"""

from __future__ import annotations

BASE_POINTS = 100
MAX_SPEED_BONUS = 50


def speed_bonus(latency_ms: int, grace_minutes: int) -> int:
    """Decaying speed bonus for a correct answer; 0 once the grace window passes.

    Answered at/before the open instant (clock skew) → full bonus. With no grace
    window configured, there is no speed regime, so the bonus is 0 thereafter.
    """
    if latency_ms <= 0:
        return MAX_SPEED_BONUS
    grace_ms = grace_minutes * 60 * 1000
    if grace_ms <= 0:
        return 0
    fraction = max(0.0, 1.0 - latency_ms / grace_ms)
    return round(MAX_SPEED_BONUS * fraction)


def score_for_answer(*, is_correct: bool, latency_ms: int, grace_minutes: int) -> int:
    """Total points for one answer: base + decaying speed bonus, or 0 if wrong."""
    if not is_correct:
        return 0
    return BASE_POINTS + speed_bonus(latency_ms, grace_minutes)
