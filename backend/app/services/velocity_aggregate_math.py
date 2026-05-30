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

"""Pure-function math for the velocity-aggregate rollup.

Lives in its own module so the orchestration (DB upsert, logging) stays
under the project's file-size cap and so the math is trivially
unit-testable without an event loop or any SQLAlchemy plumbing.
"""

import math
from dataclasses import dataclass

# Tunables — chosen to match the existing estimator constants so the
# downstream read path doesn't need a separate config knob.
SAMPLE_WINDOW_CAP: int = 50
MIN_SAMPLES_FOR_PERT_PERCENTILE: int = 10


@dataclass(frozen=True, slots=True)
class BucketSnapshot:
    """Post-update state of one velocity-aggregate bucket row."""

    sample_window: list[float]
    contributing_bud_ids: list[str]
    n_samples: int
    running_mean: float
    running_m2: float
    p50_days: float
    p70_days: float
    p85_days: float
    pert_optimistic: float
    pert_most_likely: float
    pert_pessimistic: float


def _nearest_rank_percentile(sorted_values: list[float], pct: float) -> float:
    """Nearest-rank percentile per NIST: index = ceil(n * pct) - 1.

    Avoids the ``int(n*pct)`` off-by-one that biases small-window
    percentiles upward (e.g. ``int(5*0.70)=3`` picks the 4th-of-5
    element, which is p80 not p70).
    """
    if not sorted_values:
        return 0.0
    n = len(sorted_values)
    idx = max(0, min(n - 1, math.ceil(n * pct) - 1))
    return float(sorted_values[idx])


def derive_bucket_snapshot(
    current_window: list[float],
    current_contributing: list[str],
    current_n: int,
    current_mean: float,
    current_m2: float,
    new_actual_days: float,
    new_bud_id: str,
) -> BucketSnapshot | None:
    """Compute the post-update bucket state, or None when this BUD already counted.

    Pure function — no DB access — so the upsert and the math can be
    reviewed independently and unit-tested without an event loop.
    """
    if new_bud_id in current_contributing:
        return None

    window = [*current_window, float(new_actual_days)]
    contributing = [*current_contributing, new_bud_id]
    if len(window) > SAMPLE_WINDOW_CAP:
        window = window[-SAMPLE_WINDOW_CAP:]
        contributing = contributing[-SAMPLE_WINDOW_CAP:]

    new_n = current_n + 1
    delta = new_actual_days - current_mean
    new_mean = current_mean + delta / new_n
    new_m2 = current_m2 + delta * (new_actual_days - new_mean)

    sorted_w = sorted(window)
    p50 = _nearest_rank_percentile(sorted_w, 0.50)
    p70 = _nearest_rank_percentile(sorted_w, 0.70)
    p85 = _nearest_rank_percentile(sorted_w, 0.85)

    if len(window) >= MIN_SAMPLES_FOR_PERT_PERCENTILE:
        optimistic = _nearest_rank_percentile(sorted_w, 0.05)
        pessimistic = _nearest_rank_percentile(sorted_w, 0.95)
    else:
        optimistic = sorted_w[0]
        pessimistic = sorted_w[-1]

    return BucketSnapshot(
        sample_window=window,
        contributing_bud_ids=contributing,
        n_samples=new_n,
        running_mean=new_mean,
        running_m2=new_m2,
        p50_days=p50,
        p70_days=p70,
        p85_days=p85,
        pert_optimistic=optimistic,
        pert_most_likely=p50,
        pert_pessimistic=pessimistic,
    )
