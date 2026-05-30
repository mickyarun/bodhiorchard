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

"""Pydantic DTOs for the org-level Learnings overview endpoint."""

from pydantic import BaseModel


class PhaseRollupRead(BaseModel):
    """One phase's rolling percentiles + trend within a complexity bucket."""

    phase: str
    n_samples: int
    p50_days: float | None = None
    p70_days: float | None = None
    p85_days: float | None = None
    running_mean: float | None = None
    # ``running_mean_30d_ago`` lives on the bucket row but is populated by
    # a daily snapshot job (commit 11). Surface as a delta so the FE just
    # renders "+12%" / "-8%" / "—" without doing the math.
    trend_30d_pct: float | None = None


class ComplexityBucketRead(BaseModel):
    """All phases for one complexity bucket in an org."""

    complexity: int
    n_samples_total: int
    phases: list[PhaseRollupRead]


class RepeatOffenderRead(BaseModel):
    """A phase that consistently overran its estimate across recent BUDs."""

    phase: str
    median_drift_pct: float
    buds_over_estimate: int
    buds_total: int


class VelocityTrendPointRead(BaseModel):
    """Weekly bucket of avg cycle days for the velocity trend chart."""

    week_start: str  # YYYY-MM-DD
    avg_cycle_days: float
    n_buds: int


class TopContributorRead(BaseModel):
    """One contributor's recent throughput for the leaderboard card."""

    user_id: str
    name: str
    buds_shipped_30d: int
    total_commits_30d: int
    total_prs_merged_30d: int


class LearningsOverviewRead(BaseModel):
    """Top-level shape consumed by the /learnings page."""

    complexity_buckets: list[ComplexityBucketRead] = []
    repeat_offender_phases: list[RepeatOffenderRead] = []
    velocity_trend: list[VelocityTrendPointRead] = []
    top_contributors: list[TopContributorRead] = []
