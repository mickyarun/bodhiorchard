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

"""Pure helpers used by ``bud_estimation.estimate_bud_dates``.

Split out so the orchestration entry point stays focused on the
sequencing of context → AI-PERT → Monte Carlo → persist, and so each
helper is independently unit-testable. No DB access, no LLM calls.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from app.models.bud import BUDDocument
from app.models.user import UserRole
from app.services.estimation_engine import (
    PERTEstimate,
    add_business_days,
    pert_expected,
    pert_std_dev,
    project_buffer_days,
)
from app.services.phase_roles import PHASE_ROLE_MAP

# Magennis-style mixing weight: each completed comparable BUD adds 10
# percentage points of historical influence, capped at 70 % so the LLM
# never disappears entirely (needed for novel work the team has never
# done before — first-ever multiplayer feature, etc.).
HISTORICAL_WEIGHT_PER_SAMPLE = 0.1
HISTORICAL_WEIGHT_CAP = 0.7

# Capacity narration thresholds. "Heavily loaded" fires below 20 % so the
# prompt language matches the 0.1 capacity floor in the engine without
# overpromising — anything in [0.1, 0.2] is firefighting territory.
_HEAVILY_LOADED_CAPACITY = 0.2

# Confidence calibration coefficients for the per-phase JSONB. Higher
# variance → less confidence; the 0.5 floor keeps the displayed value
# readable, the 0.95 ceiling reflects irreducible uncertainty.
_CONFIDENCE_BASE = 0.5
_CONFIDENCE_CEILING = 0.95
_CONFIDENCE_PER_INVERSE_VARIANCE = 0.1
_CONFIDENCE_VARIANCE_FLOOR = 0.1

# Defaults for the cumulative MC summary when an estimate could not be
# computed for any phase (e.g. all phases were marked complete already).
_FALLBACK_PROD_P50 = 20
_FALLBACK_PROD_P70 = 25
_FALLBACK_PROD_P85 = 30


def historical_sample_count(historical_by_phase: dict[str, list[float]]) -> int:
    """Number of distinct past BUDs feeding the historical bootstrap.

    Each phase list has the same length (one entry per past BUD), so we
    pick any list to count. Returns 0 when no history is available.
    """
    if not historical_by_phase:
        return 0
    any_list = next(iter(historical_by_phase.values()), [])
    return len(any_list)


def historical_mix_weight(historical_by_phase: dict[str, list[float]]) -> float:
    """Compute the Monte Carlo historical-vs-LLM mix weight.

    Capped so the LLM continues to provide signal for parts of the work
    the historical sample cannot represent.
    """
    n = historical_sample_count(historical_by_phase)
    return min(HISTORICAL_WEIGHT_CAP, n * HISTORICAL_WEIGHT_PER_SAMPLE)


def build_capacity_summary(
    role_capacity: dict[UserRole, float],
    remaining_phases: list[str],
) -> list[tuple[str, float, str]]:
    """Convert role-capacity floats into prompt-ready tuples.

    Filters to roles actually involved in the remaining phases so the
    prompt does not list e.g. ``DESIGNER`` capacity for a BUD that has
    already passed the design phase. Returned tuples are
    ``(role_value, capacity, narration)`` — narration is a short human
    string the prompt formatter quotes verbatim.
    """
    needed_roles = {PHASE_ROLE_MAP[p] for p in remaining_phases if p in PHASE_ROLE_MAP}
    rows: list[tuple[str, float, str]] = []
    for role in sorted(needed_roles, key=lambda r: r.value):
        capacity = role_capacity.get(role, 1.0)
        if capacity >= 1.0:
            narration = "fully available"
        elif capacity <= _HEAVILY_LOADED_CAPACITY:
            narration = "heavily loaded"
        else:
            narration = f"{int((1 - capacity) * 100)}% loaded"
        rows.append((role.value, capacity, narration))
    return rows


def parse_iso(value: str | None) -> datetime | None:
    """Parse ISO date/datetime string to datetime, or None."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None


def build_estimated_dates(
    bud: BUDDocument,
    remaining: list[str],
    pert_estimates: dict[str, PERTEstimate],
    mc_results: dict[str, dict[str, float]],
    today: date,
) -> dict[str, Any]:
    """Build the estimated_dates JSONB, preserving manual overrides.

    Phase D (Critical Chain Method): per-phase
    ``estimated_completion`` is the median (P50), not P70 — we pull the
    safety margin out of every phase and put it into a single project
    buffer at the end of the timeline. The ``commit_date`` field in
    ``_summary`` is what stakeholders should commit to: prod-P50 plus
    the aggregated √Σ buffer.
    """
    existing = dict(bud.estimated_dates or {})
    result: dict[str, Any] = {}

    for phase in remaining:
        if phase in existing and existing[phase].get("source") == "override":
            override_date = parse_iso(
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

        confidence = round(
            min(
                _CONFIDENCE_CEILING,
                _CONFIDENCE_BASE
                + (1.0 / max(std_dev, _CONFIDENCE_VARIANCE_FLOOR))
                * _CONFIDENCE_PER_INVERSE_VARIANCE,
            ),
            2,
        )
        result[phase] = {
            "estimated_completion": p50.isoformat(),
            "p50_date": p50.isoformat(),
            "p70_date": p70.isoformat(),
            "p85_date": p85.isoformat(),
            "expected_days": round(expected_days, 1),
            "std_dev_days": round(std_dev, 1),
            "source": "ai_pert",
            "confidence": confidence,
        }

    total_mc = mc_results.get("_total", {})
    phase_variances = mc_results.get("_phase_variances") or {}
    buffer_days = project_buffer_days(phase_variances)
    prod_p50_date = add_business_days(today, total_mc.get("p50", _FALLBACK_PROD_P50))
    commit_date = add_business_days(prod_p50_date, buffer_days)

    result["_summary"] = {
        "prod_p50": prod_p50_date.isoformat(),
        "prod_p70": add_business_days(today, total_mc.get("p70", _FALLBACK_PROD_P70)).isoformat(),
        "prod_p85": add_business_days(today, total_mc.get("p85", _FALLBACK_PROD_P85)).isoformat(),
        "project_buffer_days": round(buffer_days, 1),
        "commit_date": commit_date.isoformat(),
        "complexity": bud.complexity,
        "generated_at": datetime.now(UTC).isoformat(),
    }

    return result
