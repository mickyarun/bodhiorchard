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

"""AI-powered BUD lifecycle estimation service.

Orchestrates AI-PERT estimation with Monte Carlo simulation.
Delegates: context → estimation_context, math → estimation_engine,
LLM calls → estimation_llm.
"""

import uuid
from datetime import UTC, date, datetime
from typing import Any, cast

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bud import BUDDocument, BUDStatus
from app.models.bud_estimate_snapshot import BUDEstimateSnapshot
from app.repositories.organization import OrganizationRepository
from app.services.bud_estimation_helpers import (
    build_capacity_summary,
    build_estimated_dates,
    historical_mix_weight,
    historical_sample_count,
    parse_iso,
)
from app.services.bud_timeline import record_event
from app.services.capacity_provider import capacity_by_phase, get_role_loads
from app.services.estimation_context import (
    compute_bud_complexity,
    get_backlog_context,
    get_bug_context,
    get_historical_context,
    get_historical_phase_durations,
    get_skill_context,
)
from app.services.estimation_engine import monte_carlo_simulate
from app.services.estimation_gates import gate_pert, gate_turnaround_days
from app.services.estimation_heuristics import default_pert_spread, reconcile_complexity
from app.services.estimation_llm import llm_pert_estimate
from app.services.estimation_progress import current_phase_progress, discounted_pert
from app.services.org_settings import get_phase_order
from app.services.phase_roles import is_gate_phase

logger = structlog.get_logger(__name__)


async def estimate_bud_dates(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud: BUDDocument,
    trigger: str = "manual",
    actor_id: uuid.UUID | None = None,
    actor_name: str | None = None,
) -> dict[str, Any]:
    """Compute and persist per-phase estimated completion dates for a BUD.

    Orchestrates: context gathering → AI-PERT → Monte Carlo → persist.
    """
    current_status = bud.status.value if isinstance(bud.status, BUDStatus) else bud.status

    # Resolve the org's phase order (may omit "uat" if the org has it
    # toggled off via org.config.bud_stages.uat_enabled). BUDDocument has
    # no .organization relationship, so we load the org explicitly.
    org = await OrganizationRepository(db).get_by_id(org_id)
    phase_order = get_phase_order(org.config if org else None)

    # Determine remaining phases relative to the current status. If the
    # current status is itself disabled (e.g. current_status="uat" but the
    # org just turned UAT off), fall back to starting from the beginning.
    try:
        current_idx = phase_order.index(current_status)
    except ValueError:
        current_idx = 0
    remaining = phase_order[current_idx:]

    # Gather context
    backlog_ctx = await get_backlog_context(db, org_id, bud)
    skill_ctx = await get_skill_context(db, org_id, bud)
    historical_ctx = await get_historical_context(db, org_id)
    bug_ctx = await get_bug_context(db, org_id, bud)

    # Bugs feed the heuristic complexity (more work, not less throughput).
    heuristic_complexity = compute_bud_complexity(bud, bug_ctx["open_bug_count"])

    # Capacity: raw per-role pool + active load today, projected onto
    # each remaining phase via its fallback chain (PHASE_ROLE_CHAIN) and
    # the queueing curve. Both the engine (post-MC divisor) and the
    # prompt (context block for the LLM) read from the same loads —
    # single source of truth.
    role_loads = await get_role_loads(db, org_id)
    cap_by_phase = capacity_by_phase(role_loads, remaining)
    capacity_summary = build_capacity_summary(role_loads, remaining)

    # The historical sampler is fetched once and used both by the LLM
    # call (so the prompt can mention how many past BUDs are blending in)
    # and by the Monte Carlo loop further down — single source of truth.
    historical_phase_data = await get_historical_phase_durations(
        db, org_id, heuristic_complexity, remaining
    )
    historical_n = historical_sample_count(historical_phase_data)

    # AI-PERT estimation + LLM-rated complexity (with fallback). The org's
    # config is threaded through so the prompt can name the configured AI
    # coding agent (Claude Code / Ollama / Cloud / Codex) instead of
    # hardcoding one — see ``get_ai_agent_profile``.
    llm_result = await llm_pert_estimate(
        bud,
        heuristic_complexity,
        backlog_ctx,
        skill_ctx,
        historical_ctx,
        remaining,
        org_config=org.config if org else None,
        capacity_summary=capacity_summary,
        bug_context=bug_ctx,
        historical_n_used=historical_n,
    )
    if llm_result is not None:
        pert_estimates = llm_result.phases
        # Trust the LLM's independent rating, bounded to ±1 of the heuristic
        # so a short spec across many repos (which the heuristic over-scores)
        # can come back down without letting a hallucinated rating run free.
        complexity = reconcile_complexity(llm_result.complexity, heuristic_complexity)
    else:
        all_defaults = default_pert_spread(
            heuristic_complexity,
            backlog_ctx["queue_depth"],
            backlog_ctx["assignee_workload"],
            phase_order=phase_order,
        )
        pert_estimates = {p: all_defaults[p] for p in remaining if p in all_defaults}
        complexity = heuristic_complexity

    # Review-gate phases (bud/uat/code_review) are sign-off latency, not
    # effort ÷ capacity work. Override their effort PERT with a small capped
    # turnaround budget and neutralise the capacity divisor (1.0) so the
    # generic Monte Carlo engine renders gate wall-clock with no phase-kind
    # knowledge of its own. The LLM's gate effort is intentionally unused —
    # a swamped reviewer adds bounded latency, it does not multiply effort —
    # but the discarded triple is captured in the snapshot below so the
    # override is auditable. Historical wall-clock for a gate still blends in
    # downstream (those samples are already wall-clock); the turnaround is the
    # model draw, not the only source.
    gate_turnaround_by_phase: dict[str, float] = {}
    gate_llm_effort_overridden: dict[str, list[float]] = {}
    for phase in pert_estimates:
        if not is_gate_phase(phase):
            continue
        prior = pert_estimates[phase]
        gate_llm_effort_overridden[phase] = [
            prior.optimistic,
            prior.most_likely,
            prior.pessimistic,
        ]
        turnaround = gate_turnaround_days(role_loads, phase)
        gate_turnaround_by_phase[phase] = turnaround
        pert_estimates[phase] = gate_pert(turnaround)
        cap_by_phase[phase] = 1.0

    # A gate in scope but absent from pert_estimates would silently keep the
    # effort ÷ capacity model — the exact over-stretch this override exists to
    # kill. Surface that divergence rather than letting it pass unnoticed.
    missing_gates = [
        p for p in remaining if is_gate_phase(p) and p not in gate_turnaround_by_phase
    ]
    if missing_gates:
        logger.warning(
            "gate_phase_missing_from_pert_estimates",
            bud_id=str(bud.id),
            missing_gates=missing_gates,
            source="llm" if llm_result is not None else "heuristic",
            action="gate left on effort/capacity model; estimate may over-stretch it",
        )

    # Progress-aware current phase: a phase whose todos are done (or whose
    # BUD already has a merged PR for code work) shouldn't be re-budgeted at
    # full effort just because the BUD hasn't been transitioned yet. Discount
    # only the current phase by what remains; downstream phases haven't
    # started, so they stand. Applied after the gate override so it scales
    # whatever PERT the current phase ended up with (build or gate).
    current_phase_done = await current_phase_progress(db, org_id, bud)
    if current_phase_done > 0.0:
        if current_status in pert_estimates:
            pert_estimates[current_status] = discounted_pert(
                pert_estimates[current_status], current_phase_done
            )
        else:
            # Real completion was measured but the current phase has no PERT to
            # discount — the snapshot would otherwise record progress next to an
            # undiscounted estimate. Surface it, mirroring the gate-missing warn.
            logger.warning(
                "current_phase_progress_unapplied",
                bud_id=str(bud.id),
                current_status=current_status,
                progress=current_phase_done,
                pert_phases=list(pert_estimates.keys()),
                action="phase absent from pert_estimates; discount skipped",
            )

    # Historical reference-class (Magennis-style bootstrap) reuses the
    # same per-phase data fetched for the prompt above; weight ramps with
    # sample size and caps at HISTORICAL_WEIGHT_CAP so the LLM never
    # disappears — useful for novel work the team has never done before.
    historical_weight = historical_mix_weight(historical_phase_data)

    # Monte Carlo simulation — use pert_estimates keys to avoid mismatch.
    # Capacity divides each per-iteration LLM effort sample to produce
    # wall-clock days (per-iteration, not post-hoc — variance also
    # stretches when the role pool is loaded). Historical draws skip the
    # capacity divisor; they are already wall-clock.
    mc_results = monte_carlo_simulate(
        pert_estimates,
        list(pert_estimates.keys()),
        capacity_by_phase=cap_by_phase,
        historical_by_phase=historical_phase_data,
        historical_weight=historical_weight,
    )

    # Build JSONB and persist
    today = date.today()
    estimated_dates = build_estimated_dates(
        bud,
        remaining,
        pert_estimates,
        mc_results,
        today,
    )

    bud.estimated_dates = estimated_dates
    bud.complexity = complexity
    summary = estimated_dates.get("_summary", {})
    bud.prod_p70_date = parse_iso(summary.get("prod_p70"))
    bud.current_phase_deadline = parse_iso(
        (estimated_dates.get(current_status) or {}).get("p70_date")
    )
    await db.flush()

    # Audit snapshot — capacity numbers + bug count are persisted so we
    # can later answer "why did this BUD get this estimate?".
    snapshot = BUDEstimateSnapshot(
        org_id=org_id,
        bud_id=bud.id,
        trigger=trigger,
        phase_estimates=estimated_dates,
        complexity=complexity,
        context={
            "backlog": backlog_ctx,
            "skill": skill_ctx,
            "has_historical": bool(historical_ctx),
            "capacity_by_phase": cap_by_phase,
            "gate_turnaround_by_phase": gate_turnaround_by_phase,
            "gate_llm_effort_overridden": gate_llm_effort_overridden,
            "current_phase_progress": current_phase_done,
            "open_bug_count": bug_ctx["open_bug_count"],
            "historical_n_used": historical_n,
            "historical_weight": historical_weight,
        },
        actor_id=actor_id,
    )
    db.add(snapshot)

    await record_event(
        db,
        org_id,
        bud.id,
        "estimate_generated",
        actor_id=actor_id,
        actor_name=actor_name,
        detail={
            "trigger": trigger,
            "complexity": complexity,
            "prod_p70": summary.get("prod_p70"),
            "prod_p85": summary.get("prod_p85"),
        },
    )

    await db.flush()
    await db.refresh(bud)
    return estimated_dates


async def override_phase_date(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud: BUDDocument,
    phase: str,
    new_date: datetime,
    reason: str,
    actor_id: uuid.UUID,
    actor_name: str,
) -> dict[str, Any]:
    """Override a single phase's estimated date with a mandatory reason.

    Only phases enabled for this org can be overridden — e.g. a UAT-
    disabled org rejects ``phase="uat"`` so we don't accidentally write
    a stale UAT row into estimated_dates.
    """
    org = await OrganizationRepository(db).get_by_id(org_id)
    allowed_phases = get_phase_order(org.config if org else None)
    if phase not in allowed_phases:
        raise ValueError(f"Invalid phase '{phase}' for this org (allowed: {allowed_phases})")
    estimated = dict(bud.estimated_dates or {})
    old_date = (estimated.get(phase) or {}).get("estimated_completion")

    date_iso = new_date.date().isoformat() if hasattr(new_date, "date") else new_date.isoformat()
    estimated[phase] = {
        "estimated_completion": date_iso,
        "p50_date": date_iso,
        "p70_date": date_iso,
        "p85_date": date_iso,
        "source": "override",
        "confidence": 1.0,
        "override_reason": reason,
        "overridden_by": str(actor_id),
        "overridden_at": datetime.now(UTC).isoformat(),
    }
    bud.estimated_dates = estimated

    current_status = bud.status.value if isinstance(bud.status, BUDStatus) else bud.status
    if phase == current_status:
        bud.current_phase_deadline = new_date
    if phase == "prod":
        bud.prod_p70_date = new_date

    snapshot = BUDEstimateSnapshot(
        org_id=org_id,
        bud_id=bud.id,
        trigger="manual",
        phase_estimates=estimated,
        complexity=bud.complexity,
        context={"override_phase": phase, "reason": reason},
        actor_id=actor_id,
    )
    db.add(snapshot)

    await record_event(
        db,
        org_id,
        bud.id,
        "estimate_overridden",
        actor_id=actor_id,
        actor_name=actor_name,
        detail={
            "phase": phase,
            "new_date": date_iso,
            "previous_date": old_date,
            "reason": reason,
        },
    )

    await db.flush()
    await db.refresh(bud)
    return cast(dict[str, Any], estimated[phase])
