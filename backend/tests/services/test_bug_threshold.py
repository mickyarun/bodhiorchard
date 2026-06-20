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

"""Tests for ``org_settings.get_bug_threshold`` complexity resolution."""

from __future__ import annotations

from app.services.org_settings import get_bug_threshold


def test_defaults_map_each_complexity() -> None:
    assert get_bug_threshold(None, 1) == 1
    assert get_bug_threshold({}, 3) == 4
    assert get_bug_threshold({}, 5) == 9


def test_missing_complexity_clamps_to_range() -> None:
    # None → treated as level 1; out-of-range → clamped to 5.
    assert get_bug_threshold({}, None) == 1
    assert get_bug_threshold({}, 0) == 1
    assert get_bug_threshold({}, 99) == 9


def test_partial_map_falls_back_to_nearest_lower_level() -> None:
    cfg = {"qa": {"bugThresholdByComplexity": {"1": 1, "5": 10}}}
    # complexity 3 has no explicit entry → nearest lower defined is 1.
    assert get_bug_threshold(cfg, 3) == 1
    assert get_bug_threshold(cfg, 5) == 10


def test_falls_back_to_nearest_higher_when_no_lower_defined() -> None:
    cfg = {"qa": {"bugThresholdByComplexity": {"4": 6, "5": 9}}}
    # complexity 2 has no lower defined entry → nearest higher is 4 → 6.
    assert get_bug_threshold(cfg, 2) == 6
    assert get_bug_threshold(cfg, 1) == 6


def test_empty_map_falls_back_to_reject_threshold() -> None:
    cfg = {"qa": {"bugThresholdByComplexity": {}, "bugRejectThreshold": 7}}
    assert get_bug_threshold(cfg, 3) == 7


def test_custom_map_used() -> None:
    cfg = {"qa": {"bugThresholdByComplexity": {"1": 2, "2": 3, "3": 5, "4": 8, "5": 12}}}
    assert get_bug_threshold(cfg, 4) == 8
