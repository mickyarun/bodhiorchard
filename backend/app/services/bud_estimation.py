"""AI-powered BUD lifecycle estimation service.

Orchestrates AI-PERT estimation with Monte Carlo simulation.
Delegates: context → estimation_context, math → estimation_engine,
LLM calls → estimation_llm.
"""

import uuid
from datetime import UTC, date, datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bud import BUDDocument, BUDStatus
from app.models.bud_estimate_snapshot import BUDEstimateSnapshot
from app.repositories.organization import OrganizationRepository
from app.services.bud_timeline import record_event
from app.services.estimation_context import (
    compute_bud_complexity,
    get_backlog_context,
    get_historical_context,
    get_skill_context,
)
from app.services.estimation_engine import (
    PERTEstimate,
    add_business_days,
    default_pert_spread,
    monte_carlo_simulate,
    pert_expected,
    pert_std_dev,
)
from app.services.estimation_llm import llm_pert_estimate
from app.services.org_settings import get_phase_order

logger = structlog.get_logger(__name__)


async def estimate_bud_dates(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud: BUDDocument,
    trigger: str = "manual",
    actor_id: uuid.UUID | None = None,
    actor_name: str | None = None,
) -> dict:
    """Compute and persist per-phase estimated completion dates for a BUD.

    Orchestrates: context gathering → AI-PERT → Monte Carlo → persist.
    """
    heuristic_complexity = compute_bud_complexity(bud)
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

    # AI-PERT estimation + LLM-rated complexity (with fallback)
    llm_result = await llm_pert_estimate(
        bud,
        heuristic_complexity,
        backlog_ctx,
        skill_ctx,
        historical_ctx,
        remaining,
    )
    if llm_result is not None:
        pert_estimates = llm_result.phases
        complexity = llm_result.complexity or heuristic_complexity
    else:
        all_defaults = default_pert_spread(
            heuristic_complexity,
            backlog_ctx["queue_depth"],
            backlog_ctx["assignee_workload"],
            phase_order=phase_order,
        )
        pert_estimates = {p: all_defaults[p] for p in remaining if p in all_defaults}
        complexity = heuristic_complexity

    # Monte Carlo simulation — use pert_estimates keys to avoid mismatch
    mc_results = monte_carlo_simulate(pert_estimates, list(pert_estimates.keys()))

    # Build JSONB and persist
    today = date.today()
    estimated_dates = _build_estimated_dates(
        bud,
        remaining,
        pert_estimates,
        mc_results,
        today,
    )

    bud.estimated_dates = estimated_dates
    bud.complexity = complexity
    summary = estimated_dates.get("_summary", {})
    bud.prod_p70_date = _parse_iso(summary.get("prod_p70"))
    bud.current_phase_deadline = _parse_iso(
        (estimated_dates.get(current_status) or {}).get("p70_date")
    )
    await db.flush()

    # Audit snapshot
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
) -> dict:
    """Override a single phase's estimated date with a mandatory reason.

    Only phases enabled for this org can be overridden — e.g. a UAT-
    disabled org rejects ``phase="uat"`` so we don't accidentally write
    a stale UAT row into estimated_dates.
    """
    org = await OrganizationRepository(db).get_by_id(org_id)
    allowed_phases = get_phase_order(org.config if org else None)
    if phase not in allowed_phases:
        raise ValueError(
            f"Invalid phase '{phase}' for this org (allowed: {allowed_phases})"
        )
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
    return estimated[phase]


# ── Private Helpers ─────────────────────────────────────────────


def _build_estimated_dates(
    bud: BUDDocument,
    remaining: list[str],
    pert_estimates: dict[str, PERTEstimate],
    mc_results: dict[str, dict[str, float]],
    today: date,
) -> dict:
    """Build the estimated_dates JSONB, preserving manual overrides."""
    existing = dict(bud.estimated_dates or {})
    result: dict = {}

    for phase in remaining:
        if phase in existing and existing[phase].get("source") == "override":
            override_date = _parse_iso(
                existing[phase].get("estimated_completion"),
            )
            if override_date and override_date.date() >= today:
                result[phase] = existing[phase]
                continue

        est = pert_estimates.get(phase)
        mc = mc_results.get(phase, {})
        if not est:
            continue

        expected_days = pert_expected(est)
        std_dev = pert_std_dev(est)
        p50 = add_business_days(today, mc.get("p50", expected_days))
        p70 = add_business_days(today, mc.get("p70", expected_days))
        p85 = add_business_days(today, mc.get("p85", expected_days))

        result[phase] = {
            "estimated_completion": p70.isoformat(),
            "p50_date": p50.isoformat(),
            "p70_date": p70.isoformat(),
            "p85_date": p85.isoformat(),
            "expected_days": round(expected_days, 1),
            "std_dev_days": round(std_dev, 1),
            "source": "ai_pert",
            "confidence": round(
                min(0.95, 0.5 + (1.0 / max(std_dev, 0.1)) * 0.1),
                2,
            ),
        }

    total_mc = mc_results.get("_total", {})
    result["_summary"] = {
        "prod_p50": add_business_days(
            today,
            total_mc.get("p50", 20),
        ).isoformat(),
        "prod_p70": add_business_days(
            today,
            total_mc.get("p70", 25),
        ).isoformat(),
        "prod_p85": add_business_days(
            today,
            total_mc.get("p85", 30),
        ).isoformat(),
        "complexity": bud.complexity,
        "generated_at": datetime.now(UTC).isoformat(),
    }

    return result


def _parse_iso(value: str | None) -> datetime | None:
    """Parse ISO date/datetime string to datetime, or None."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None
