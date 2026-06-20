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

"""Tests for the shared phase-on-time helper."""

from __future__ import annotations

from types import SimpleNamespace

from app.services.phase_timing import phase_drift_on_time


def _learning(metrics: dict | None):
    return SimpleNamespace(metrics=metrics)


def test_on_or_under_estimate_is_on_time() -> None:
    learning = _learning({"phase_metrics": {"development": {"drift_pct": -10.0}}})
    assert phase_drift_on_time(learning, "development") is True
    learning0 = _learning({"phase_metrics": {"development": {"drift_pct": 0.0}}})
    assert phase_drift_on_time(learning0, "development") is True


def test_overrun_is_not_on_time() -> None:
    learning = _learning({"phase_metrics": {"development": {"drift_pct": 15.0}}})
    assert phase_drift_on_time(learning, "development") is False


def test_missing_data_is_not_on_time() -> None:
    assert phase_drift_on_time(None, "development") is False
    assert phase_drift_on_time(_learning(None), "development") is False
    assert phase_drift_on_time(_learning({"phase_metrics": {}}), "development") is False
    # phase present but no drift recorded
    no_drift = _learning({"phase_metrics": {"development": {}}})
    assert phase_drift_on_time(no_drift, "development") is False


def test_other_phase_not_consulted() -> None:
    learning = _learning({"phase_metrics": {"design": {"drift_pct": -5.0}}})
    assert phase_drift_on_time(learning, "tech_arch") is False
    assert phase_drift_on_time(learning, "design") is True
