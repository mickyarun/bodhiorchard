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

"""Was a BUD phase delivered within its estimate?

Shared by every on-time SP rule (developer quality, PM tech-spec, designer,
tech-arch) so they all read the same ``phase_metrics[phase].drift_pct`` shape
the post-close metrics envelope writes — one definition of "on time".
"""

from __future__ import annotations

from typing import Any

from app.models.feature_learning import FeatureLearning


def phase_drift_on_time(learning: FeatureLearning | None, phase: str) -> bool:
    """True when ``phase`` landed on or under its first estimate (drift ≤ 0).

    A missing envelope or missing estimate for the phase returns ``False`` —
    on-time bonuses are earned against real data, never assumed.
    """
    if learning is None or not learning.metrics:
        return False
    phase_metrics: dict[str, Any] = learning.metrics.get("phase_metrics") or {}
    entry: dict[str, Any] = phase_metrics.get(phase) or {}
    drift = entry.get("drift_pct")
    return isinstance(drift, (int, float)) and drift <= 0
