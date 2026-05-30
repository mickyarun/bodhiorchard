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

"""Context gathering for BUD estimation.

Collects backlog depth, assignee workload, developer skill profiles,
and historical calibration data to feed the estimation engine.
"""

import uuid
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bud import BUDDocument, BUDStatus
from app.models.bug import BugStatus
from app.models.velocity_aggregate import VelocityAggregate
from app.repositories.bud import BUDRepository
from app.repositories.bud_estimate import BUDEstimateQueryRepository
from app.repositories.bug import BugRepository
from app.repositories.skill_profile import SkillProfileRepository
from app.repositories.velocity_aggregate import VelocityAggregateRepository
from app.services.estimation_engine import DEFAULT_PHASE_DAYS
from app.services.estimation_heuristics import compute_complexity

logger = structlog.get_logger(__name__)

_TERMINAL_STATUSES = {BUDStatus.CLOSED, BUDStatus.DISCARDED, BUDStatus.PROD}

# Phases where developer SkillProfile data improves estimates.
SKILL_AWARE_PHASES = {"development", "code_review", "testing"}

# How many open bugs against this BUD bump the heuristic complexity by 1.
# Five was chosen to mirror ``QAAutomationSettings.bug_reject_threshold``'s
# default — once the bug count is in "auto-reject from testing" territory,
# the BUD is materially harder than its PRD alone implies.
BUG_COMPLEXITY_BUCKET = 5

# Open-bug statuses that count toward the complexity bump. We exclude
# RESOLVED / CLOSED (no longer real work) and BLOCKED (work that is not
# this team's to do). IN_PROGRESS counts because it is in-flight work the
# estimator still needs to absorb.
_OPEN_BUG_STATUSES = (BugStatus.OPEN, BugStatus.IN_PROGRESS)


def compute_bud_complexity(bud: BUDDocument, open_bug_count: int = 0) -> int:
    """Derive complexity score from BUD content signals plus open bugs.

    Bugs are *more work*, not less throughput, so they belong on the
    complexity axis (which the estimator already knows how to scale)
    rather than on the capacity axis. ``open_bug_count`` defaults to 0
    so existing callers that have not been updated keep working —
    behaviour-preserving.
    """
    qa_count = len(bud.qa_automation_cases or []) + len(bud.qa_manual_cases or [])
    base = compute_complexity(
        requirements_len=len(bud.requirements_md or ""),
        tech_spec_len=len(bud.tech_spec_md or ""),
        impacted_repo_count=len(bud.impacted_repos or []),
        qa_case_count=qa_count,
    )
    bug_bump = open_bug_count // BUG_COMPLEXITY_BUCKET
    return min(5, base + bug_bump)


async def get_bug_context(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud: BUDDocument,
) -> dict[str, Any]:
    """Count open bugs linked to this BUD, returning a dict for the prompt.

    A single aggregate query — no per-bug iteration. Returns
    ``{"open_bug_count": int}``; future fields (e.g. severity breakdown,
    per-module counts) slot in here without touching call sites.
    """
    open_count = await BugRepository(db, org_id=org_id).count_open_for_bud_with_statuses(
        bud.id, _OPEN_BUG_STATUSES
    )
    return {"open_bug_count": open_count}


async def get_backlog_context(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud: BUDDocument,
) -> dict[str, Any]:
    """Gather backlog depth and assignee workload."""
    est_repo = BUDEstimateQueryRepository(db, org_id=org_id)
    status_val = bud.status.value if isinstance(bud.status, BUDStatus) else bud.status
    queue_depth = await est_repo.count_ahead_in_queue(bud.bud_number, status_val)

    assignee_workload = 0
    if bud.assignee_id:
        assignee_workload = await BUDRepository(db, org_id=org_id).count_assignee_workload(
            bud.assignee_id,
            [s.value for s in _TERMINAL_STATUSES],
            exclude_bud_id=bud.id,
        )

    return {"queue_depth": queue_depth, "assignee_workload": assignee_workload}


async def get_skill_context(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud: BUDDocument,
) -> dict[str, Any] | None:
    """Get assignee's skill profile data for skill-aware phases."""
    current_status = bud.status.value if isinstance(bud.status, BUDStatus) else bud.status
    if current_status not in SKILL_AWARE_PHASES or not bud.assignee_id:
        return None

    # Get assignee's skill profiles directly — no LLM call needed.
    # The estimation LLM reads the tech spec and judges relevance itself.
    assignee_skills = await SkillProfileRepository(db, org_id=org_id).list_for_user(
        bud.assignee_id
    )
    modules = {sp.module.lower() for sp in assignee_skills}

    return {
        "modules_known": list(modules),
        "module_count": len(assignee_skills),
        "avg_skill_score": (
            sum(float(sp.skill_score) for sp in assignee_skills) / len(assignee_skills)
            if assignee_skills
            else 0.0
        ),
        "skill_details": [
            {
                "module": sp.module,
                "score": float(sp.skill_score),
                "touches": sp.touch_count,
                "languages": sp.languages or [],
            }
            for sp in assignee_skills
        ],
    }


async def get_historical_context(
    db: AsyncSession,
    org_id: uuid.UUID,
) -> str:
    """Build few-shot historical context from completed BUDs (if any)."""
    completed = await BUDRepository(db, org_id=org_id).list_recent_completed(limit=5)
    if not completed:
        return ""

    lines = ["Historical data from completed features in this org:"]
    for b in completed:
        complexity = b.complexity or "?"
        cycle = max(1, (b.updated_at - b.created_at).days) if b.created_at else 0
        lines.append(f"- Feature (complexity {complexity}): completed in ~{cycle} days")
    return "\n".join(lines)


# How wide a complexity bucket is when matching past BUDs to the one
# being estimated. ±1 keeps the bucket dense enough to fire after only a
# handful of completed BUDs while still excluding the wildly different
# end of the scale (a complexity-1 BUD's cycle time tells us nothing
# about a complexity-5 BUD).
_COMPLEXITY_BUCKET_HALF_WIDTH = 1

# Cap on how many completed BUDs to pull. 50 is enough to avoid sampling
# noise while keeping the query bounded — Magennis suggests "a few dozen"
# is the sweet spot for cycle-time bootstrap forecasting.
_HISTORICAL_LIMIT = 50

# A phase needs at least this many real per-phase samples in the rollup
# before we trust it over the proportional-split approximation. Below
# this threshold the rollup may be biased by single-BUD outliers, so we
# top up with the legacy split to preserve estimate stability on fresh
# orgs and rarely-touched phases.
MIN_SAMPLES_FOR_TRUSTED = 5


def _aggregate_to_phase_key(agg: VelocityAggregate) -> str:
    """Stringify the bucket's phase enum back to the engine's key shape."""
    return agg.phase.value if hasattr(agg.phase, "value") else str(agg.phase)


async def _legacy_proportional_split(
    db: AsyncSession,
    org_id: uuid.UUID,
    low: int,
    high: int,
    phases: list[str],
) -> dict[str, list[float]]:
    """Original cycle-time bootstrap, kept as the fallback for fresh orgs.

    Pulls completed BUDs in the complexity bucket, derives per-phase
    durations by proportionally splitting whole-BUD cycle time across
    ``DEFAULT_PHASE_DAYS``. Used as a top-up when the per-phase rollup
    doesn't yet have enough samples — see ``get_historical_phase_durations``.
    """
    completed = await BUDRepository(db, org_id=org_id).list_completed_in_complexity_range(
        low, high, limit=_HISTORICAL_LIMIT
    )
    if not completed:
        return {p: [] for p in phases}

    relevant = [p for p in phases if p in DEFAULT_PHASE_DAYS]
    total_default = sum(DEFAULT_PHASE_DAYS[p] for p in relevant)
    if total_default <= 0:
        return {p: [] for p in phases}

    out: dict[str, list[float]] = {p: [] for p in phases}
    for b in completed:
        cycle = max(1.0, float((b.updated_at - b.created_at).days))
        for phase in relevant:
            share = DEFAULT_PHASE_DAYS[phase] / total_default
            out[phase].append(cycle * share)
    return out


async def get_historical_phase_durations(
    db: AsyncSession,
    org_id: uuid.UUID,
    target_complexity: int,
    phase_order: list[str],
) -> dict[str, list[float]]:
    """Per-phase wall-clock durations from past BUDs in the same complexity bucket.

    Reads the precomputed ``velocity_aggregates`` rollup first (one
    indexed scan over a tiny table) and emits the bucket's
    ``sample_window`` as the bootstrap distribution for each phase. The
    Monte Carlo loop bootstraps over these durations directly, so
    preserving the per-BUD shape is important — emitting just p50/p70
    would collapse the distribution to a point estimate.

    Phases below ``MIN_SAMPLES_FOR_TRUSTED`` fall back to the legacy
    proportional split so fresh orgs and rarely-touched phases keep
    estimate stability. The transition is logged via
    ``historical_phase_durations_loaded`` with a per-phase ``source``
    label so we can observe orgs moving from proportional to aggregates
    as real data accumulates.

    Returns ``{phase: [duration_in_days, ...]}``. Empty dict only when
    BOTH the rollup AND the legacy fallback yield no data — caller
    should treat empty as "fall back to LLM-only" (zero historical_weight).
    """
    if not phase_order:
        return {}

    low = max(1, target_complexity - _COMPLEXITY_BUCKET_HALF_WIDTH)
    high = min(5, target_complexity + _COMPLEXITY_BUCKET_HALF_WIDTH)
    relevant_phases = [p for p in phase_order if p in DEFAULT_PHASE_DAYS]

    # 1) Read the rollup first — one indexed scan over ≤40 rows.
    phase_enums = [BUDStatus(p) for p in relevant_phases if p in {s.value for s in BUDStatus}]
    aggregates = await VelocityAggregateRepository(db, org_id=org_id).list_for_complexity_range(
        low, high, phase_enums
    )

    out: dict[str, list[float]] = {p: [] for p in relevant_phases}
    rollup_sources: dict[str, int] = {}
    for agg in aggregates:
        phase_key = _aggregate_to_phase_key(agg)
        if phase_key not in out:
            continue
        if agg.n_samples < MIN_SAMPLES_FOR_TRUSTED:
            continue
        window = [float(x) for x in (agg.sample_window or [])]
        if not window:
            continue
        out[phase_key].extend(window)
        rollup_sources[phase_key] = len(window)

    # 2) Top up phases that don't have enough rollup samples. The
    # legacy split is best-effort — empty result is fine, just means
    # the bucket is genuinely empty and the engine falls back to
    # LLM-only for those phases.
    short_phases = [p for p in relevant_phases if len(out[p]) < MIN_SAMPLES_FOR_TRUSTED]
    if short_phases:
        legacy = await _legacy_proportional_split(db, org_id, low, high, short_phases)
        for phase, durations in legacy.items():
            out[phase].extend(durations)

    # Strip phases that still have zero samples so callers can use
    # ``not result[phase]`` as the "no signal" check, matching the
    # legacy contract.
    out = {p: v for p, v in out.items() if v}

    if out:
        source_per_phase = {
            p: ("aggregates" if rollup_sources.get(p) else "proportional") for p in out
        }
        logger.info(
            "historical_phase_durations_loaded",
            org_id=str(org_id),
            target_complexity=target_complexity,
            phases=source_per_phase,
        )

    return out
