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

"""Org-level Learnings overview endpoint.

Renders structural trends across many closed BUDs: which complexity
bucket is dominant, which phase consistently overruns its estimate,
how the team's velocity has trended over the last quarter, and which
contributors shipped the most. All queries live in
``LearningsOverviewRepository``; this module is thin orchestration.
"""

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.bud import BUDDocument
from app.models.user import User
from app.repositories.learnings_overview import LearningsOverviewRepository
from app.schemas.learnings import (
    ComplexityBucketRead,
    LearningsOverviewRead,
    PhaseRollupRead,
    RepeatOffenderRead,
    TopContributorRead,
    VelocityTrendPointRead,
)

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["learnings"])

# What counts as "the phase materially overran its estimate" for the
# repeat-offender table. Matches the threshold the technical-writer
# skill uses when narrating Phase Drift, so the user sees consistent
# numbers between the per-BUD recap and the org-level dashboard.
DRIFT_OFFENDER_THRESHOLD_PCT: float = 30.0


def _trend_pct(current: float | None, baseline: float | None) -> float | None:
    """Percentage delta between current running_mean and the 30-day snapshot."""
    if current is None or baseline is None or baseline <= 0:
        return None
    return round(((float(current) - float(baseline)) / float(baseline)) * 100.0, 1)


def _group_buckets_by_complexity(
    buckets: list[Any],
) -> list[ComplexityBucketRead]:
    grouped: dict[int, list[PhaseRollupRead]] = defaultdict(list)
    sample_totals: dict[int, int] = defaultdict(int)
    for row in buckets:
        phase_value = row.phase.value if hasattr(row.phase, "value") else str(row.phase)
        grouped[row.complexity].append(
            PhaseRollupRead(
                phase=phase_value,
                n_samples=row.n_samples,
                p50_days=float(row.p50_days) if row.p50_days is not None else None,
                p70_days=float(row.p70_days) if row.p70_days is not None else None,
                p85_days=float(row.p85_days) if row.p85_days is not None else None,
                running_mean=(float(row.running_mean) if row.running_mean is not None else None),
                trend_30d_pct=_trend_pct(
                    row.running_mean,
                    row.running_mean_30d_ago,
                ),
            )
        )
        sample_totals[row.complexity] += row.n_samples
    return [
        ComplexityBucketRead(
            complexity=complexity,
            n_samples_total=sample_totals[complexity],
            phases=sorted(phases, key=lambda p: p.phase),
        )
        for complexity, phases in sorted(grouped.items())
    ]


def _build_repeat_offenders(learnings: list[Any]) -> list[RepeatOffenderRead]:
    drift_by_phase: dict[str, list[float]] = defaultdict(list)
    over_by_phase: dict[str, int] = defaultdict(int)
    total_by_phase: dict[str, int] = defaultdict(int)
    for learning in learnings:
        phase_metrics = (learning.metrics or {}).get("phase_metrics") or {}
        for phase, metric in phase_metrics.items():
            if not isinstance(metric, dict):
                continue
            drift = metric.get("drift_pct")
            if drift is None:
                continue
            drift_value = float(drift)
            total_by_phase[phase] += 1
            drift_by_phase[phase].append(drift_value)
            if drift_value > DRIFT_OFFENDER_THRESHOLD_PCT:
                over_by_phase[phase] += 1

    offenders: list[RepeatOffenderRead] = []
    for phase, drifts in drift_by_phase.items():
        if not drifts:
            continue
        # Median in plain Python — drifts is at most RECENT_BUDS_LIMIT
        # entries, so sort cost is negligible and avoids dragging numpy
        # into the request path.
        sorted_drifts = sorted(drifts)
        midpoint = len(sorted_drifts) // 2
        median = (
            sorted_drifts[midpoint]
            if len(sorted_drifts) % 2 == 1
            else (sorted_drifts[midpoint - 1] + sorted_drifts[midpoint]) / 2
        )
        offenders.append(
            RepeatOffenderRead(
                phase=phase,
                median_drift_pct=round(float(median), 1),
                buds_over_estimate=over_by_phase[phase],
                buds_total=total_by_phase[phase],
            )
        )
    # Surface only phases where >= 2 BUDs overran — single-BUD drift
    # isn't a "repeat" pattern. Sort by median drift descending so the
    # worst offender renders first.
    return sorted(
        [o for o in offenders if o.buds_over_estimate >= 2],
        key=lambda o: o.median_drift_pct,
        reverse=True,
    )


def _week_key(ts: datetime) -> str:
    """ISO week-start (Monday) so weekly buckets line up cross-org.

    ``ts.weekday()`` returns 0 for Monday, so subtracting that many
    days lands on the previous Monday regardless of the supplied
    weekday. ``.date()`` discards the time component for stable
    bucket labels.
    """
    monday = (ts - timedelta(days=ts.weekday())).date()
    return monday.isoformat()


def _build_velocity_trend(buds: list[BUDDocument]) -> list[VelocityTrendPointRead]:
    per_week: dict[str, list[float]] = defaultdict(list)
    for bud in buds:
        if bud.created_at is None or bud.updated_at is None:
            continue
        cycle_days = (bud.updated_at - bud.created_at).total_seconds() / 86_400.0
        if cycle_days <= 0:
            continue
        per_week[_week_key(bud.updated_at)].append(cycle_days)
    return [
        VelocityTrendPointRead(
            week_start=week,
            avg_cycle_days=round(sum(days) / len(days), 2),
            n_buds=len(days),
        )
        for week, days in sorted(per_week.items())
    ]


def _build_top_contributors(
    rows: list[tuple[User, int, int, int]],
) -> list[TopContributorRead]:
    return [
        TopContributorRead(
            user_id=str(user.id),
            name=user.name or user.email,
            buds_shipped_30d=buds,
            total_commits_30d=commits,
            total_prs_merged_30d=prs,
        )
        for user, buds, commits, prs in rows
    ]


# Intentionally no permission gate: every org member sees the org-wide
# retrospective. The response is aggregate-only (velocity buckets, phase
# drift, contributor leaderboard) and the repo is scoped to
# current_user.org_id. If you ever add admin-only fields to
# LearningsOverviewRead, re-introduce a require_permissions dependency.
@router.get(
    "/overview",
    response_model=LearningsOverviewRead,
)
async def get_learnings_overview(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LearningsOverviewRead:
    """Aggregated org-level learning trends for the /learnings page.

    Reads the velocity_aggregates rollup directly (single indexed
    scan) and walks the last RECENT_BUDS_LIMIT feature_learnings rows
    for the trend / repeat-offender / contributor cards. Empty-state
    is the canonical cold-state — the FE renders an AppCallout when
    every field is empty.
    """
    repo = LearningsOverviewRepository(db, org_id=current_user.org_id)
    buckets = await repo.list_velocity_buckets()
    learnings = await repo.list_recent_learnings_with_metrics()
    closed_buds = await repo.list_recent_closed_buds()
    contributors = await repo.list_top_contributors_recent()

    return LearningsOverviewRead(
        complexity_buckets=_group_buckets_by_complexity(buckets),
        repeat_offender_phases=_build_repeat_offenders(learnings),
        velocity_trend=_build_velocity_trend(closed_buds),
        top_contributors=_build_top_contributors(contributors),
    )
