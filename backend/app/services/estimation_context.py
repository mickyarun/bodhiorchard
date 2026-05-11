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

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bud import BUDDocument, BUDStatus
from app.models.bug import BugStatus
from app.repositories.bud import BUDRepository
from app.repositories.bud_estimate import BUDEstimateQueryRepository
from app.repositories.bug import BugRepository
from app.repositories.skill_profile import SkillProfileRepository
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
) -> dict:
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
) -> dict:
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
) -> dict | None:
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


async def get_historical_phase_durations(
    db: AsyncSession,
    org_id: uuid.UUID,
    target_complexity: int,
    phase_order: list[str],
) -> dict[str, list[float]]:
    """Per-phase wall-clock durations from past BUDs in the same complexity bucket.

    For each completed BUD in the ±1 complexity bucket, derives a
    per-phase wall-clock duration by splitting the whole-BUD cycle time
    proportionally across phases via ``DEFAULT_PHASE_DAYS``. This is the
    Magennis "bootstrap from history" signal that the Monte Carlo loop
    mixes with the LLM's PERT triple.

    Why proportional split rather than per-phase timeline parsing:
    timeline events would give finer-grained truth but require a join
    (or N+1 reads) and parsing logic for status-transition events. The
    proportional split is a defensible v1 — it preserves the relative
    shape of phases while using the only ground-truth signal we have at
    BUD granularity (created_at → updated_at). When more accurate
    per-phase data becomes useful, this helper is the single place to
    change without touching the engine.

    Returns ``{phase: [duration_in_days, ...]}``. Empty dict when the
    bucket has no completed BUDs — caller should treat empty as "fall
    back to LLM-only" (zero historical_weight).
    """
    low = max(1, target_complexity - _COMPLEXITY_BUCKET_HALF_WIDTH)
    high = min(5, target_complexity + _COMPLEXITY_BUCKET_HALF_WIDTH)
    completed = await BUDRepository(db, org_id=org_id).list_completed_in_complexity_range(
        low, high, limit=_HISTORICAL_LIMIT
    )
    if not completed:
        return {}

    relevant_phases = [p for p in phase_order if p in DEFAULT_PHASE_DAYS]
    total_default = sum(DEFAULT_PHASE_DAYS[p] for p in relevant_phases)
    if total_default <= 0:
        return {}

    out: dict[str, list[float]] = {p: [] for p in relevant_phases}
    for b in completed:
        cycle = max(1.0, float((b.updated_at - b.created_at).days))
        for phase in relevant_phases:
            share = DEFAULT_PHASE_DAYS[phase] / total_default
            out[phase].append(cycle * share)
    return out
