# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Pure computation engine for PERT and Monte Carlo estimation.

No database access, no LLM calls — just math. This keeps the estimation
logic testable and deterministic (seed-able for reproducible tests).
"""

import math
import random
import statistics
from datetime import date, timedelta
from typing import NamedTuple

# Default business-day durations per phase when no historical data exists.
DEFAULT_PHASE_DAYS: dict[str, float] = {
    "bud": 2,
    "design": 3,
    "tech_arch": 2,
    "development": 5,
    "code_review": 2,
    "testing": 3,
    "uat": 2,
    "prod": 1,
}

# Ordered non-terminal lifecycle phases.
PHASE_ORDER: list[str] = [
    "bud",
    "design",
    "tech_arch",
    "development",
    "code_review",
    "testing",
    "uat",
    "prod",
]


class PERTEstimate(NamedTuple):
    """Three-point PERT estimate for a single phase."""

    optimistic: float
    most_likely: float
    pessimistic: float


def pert_expected(est: PERTEstimate) -> float:
    """PERT weighted average: (O + 4M + P) / 6."""
    return (est.optimistic + 4 * est.most_likely + est.pessimistic) / 6


def pert_std_dev(est: PERTEstimate) -> float:
    """PERT standard deviation: (P - O) / 6."""
    return (est.pessimistic - est.optimistic) / 6


# Vose's Beta-PERT shape parameter. The canonical value λ=4 makes the
# Beta-PERT distribution's mean equal the PERT expected value
# (O + 4M + P) / 6, which keeps `beta_pert_sample` and `pert_expected`
# mathematically consistent. See https://www.riskamp.com/beta-pert/ for
# the derivation.
_BETA_PERT_LAMBDA = 4.0

# Wall-clock divisor floor for capacity-aware Monte Carlo. A capacity
# below this would imply a >10× stretch — past the point where
# deterministic forecasting is meaningful. Lives here (the lower-level
# engine module) so ``capacity_provider`` can import it without creating
# a cycle.
MIN_CAPACITY = 0.1


def beta_pert_sample(
    rng: random.Random,
    optimistic: float,
    most_likely: float,
    pessimistic: float,
) -> float:
    """Draw a single sample from the Vose Beta-PERT distribution.

    Shape parameters follow the standard Vose form with λ=4:
        α = 1 + λ·(M − O)/(P − O)
        β = 1 + λ·(P − M)/(P − O)
    The sample is then `O + (P − O) · Beta(α, β)`.

    Beta-PERT is preferred over a triangular distribution for project
    three-point estimates because it places more weight on the mode and
    smoother weight in the tails, producing ~8–15 % better P80 accuracy
    in published schedule-risk studies (RiskAMP, Safran).

    Zero-spread input (O = M = P) short-circuits to the single value —
    otherwise the α/β formulae divide by zero.
    """
    spread = pessimistic - optimistic
    if spread <= 0:
        return optimistic
    alpha = 1.0 + _BETA_PERT_LAMBDA * (most_likely - optimistic) / spread
    beta = 1.0 + _BETA_PERT_LAMBDA * (pessimistic - most_likely) / spread
    return optimistic + spread * rng.betavariate(alpha, beta)


def historical_sample(rng: random.Random, samples: list[float]) -> float:
    """Bootstrap draw — pick one wall-clock duration from past data.

    The returned value is **already wall-clock**, so callers must not
    apply the capacity divisor to it (capacity was already baked into the
    historical observation when the team actually delivered that BUD).
    Empty list raises IndexError; callers are expected to gate on length.
    """
    return rng.choice(samples)


def monte_carlo_simulate(
    pert_estimates: dict[str, PERTEstimate],
    remaining_phases: list[str],
    n: int = 10_000,
    seed: int | None = None,
    *,
    capacity_by_phase: dict[str, float] | None = None,
    historical_by_phase: dict[str, list[float]] | None = None,
    historical_weight: float = 0.0,
) -> dict[str, dict[str, float]]:
    """Run Monte Carlo simulation over PERT estimates.

    Returns per-phase and cumulative percentile results (p50, p70, p85)
    in business days from today.

    Capacity (Phase B): when ``capacity_by_phase`` is provided, each
    phase's effort sample is divided by that phase's capacity in
    [MIN_CAPACITY, 1.0] before being summed — turning effort days into
    wall-clock days. Per-iteration division (not post-hoc multiplication
    on percentiles) so the variance also stretches when capacity is low;
    distinguishes proper resource-aware Monte Carlo from a naive
    after-the-fact multiplier (Salute Enterprises, Intaver).

    Historical reference-class (Phase C, Magennis): when
    ``historical_by_phase`` lists past wall-clock durations for a phase,
    each iteration draws from history with probability
    ``historical_weight`` (0–1), otherwise from the LLM Beta-PERT.
    Historical draws skip the capacity divisor — they are already
    wall-clock. ``historical_weight = 0.0`` (default) preserves the
    Phase-A/B behaviour exactly.
    """
    rng = random.Random(seed)
    phase_samples: dict[str, list[float]] = {p: [] for p in remaining_phases}
    # Per-phase deltas (each iteration's contribution alone, not the
    # cumulative-through-phase). Needed by Phase D's project-buffer
    # math, which assumes phase variances are independent and aggregates
    # them via √Σ.
    phase_delta_samples: dict[str, list[float]] = {p: [] for p in remaining_phases}
    cumulative_samples: list[float] = []
    cap = capacity_by_phase or {}
    hist = historical_by_phase or {}

    for _ in range(n):
        total = 0.0
        for phase in remaining_phases:
            est = pert_estimates[phase]
            phase_hist = hist.get(phase) or []
            use_historical = (
                phase_hist and historical_weight > 0.0 and rng.random() < historical_weight
            )
            if use_historical:
                # Already wall-clock — skip the capacity divisor.
                sampled = historical_sample(rng, phase_hist)
            elif est.optimistic == est.pessimistic == 0:
                sampled = 0.0
            else:
                effort = beta_pert_sample(rng, est.optimistic, est.most_likely, est.pessimistic)
                # Capacity divisor: effort days → wall-clock days. Floor
                # at MIN_CAPACITY so we never divide by ~0; also matches
                # the floor enforced by ``capacity_provider``.
                divisor = max(cap.get(phase, 1.0), MIN_CAPACITY)
                sampled = effort / divisor
            phase_samples[phase].append(total + sampled)
            phase_delta_samples[phase].append(sampled)
            total += sampled
        cumulative_samples.append(total)

    def percentiles(samples: list[float]) -> dict[str, float]:
        s = sorted(samples)
        return {
            "p50": s[int(len(s) * 0.50)],
            "p70": s[int(len(s) * 0.70)],
            "p85": s[int(len(s) * 0.85)],
        }

    result: dict[str, dict[str, float]] = {}
    for phase in remaining_phases:
        result[phase] = percentiles(phase_samples[phase])
    result["_total"] = percentiles(cumulative_samples)
    # Per-phase variance is exposed under a private key so the caller
    # can compute Goldratt's project buffer without re-running MC.
    # ``statistics.variance`` requires n ≥ 2; n is always 10k here.
    result["_phase_variances"] = {
        phase: statistics.variance(phase_delta_samples[phase]) for phase in remaining_phases
    }
    return result


# Goldratt's recommended project-buffer multiplier on the aggregated
# √Σ standard deviation. 1.5 is the canonical Critical Chain Method
# value — large enough to absorb realistic variance without bloating the
# committed date. Lives here so the project-buffer math is in one place.
PROJECT_BUFFER_FACTOR = 1.5


def project_buffer_days(
    phase_variances: dict[str, float] | list[float],
    factor: float = PROJECT_BUFFER_FACTOR,
) -> float:
    """Critical Chain project buffer: factor · √Σ(phase_variance).

    The √Σ form assumes phase variances are independent, which is the
    standard first approximation. Empty input returns 0 (no buffer
    needed when there is nothing to absorb), so partially-completed
    BUDs whose phase list is empty render cleanly as buffer = 0 rather
    than crashing the panel.

    Accepts either a list of variances or a phase→variance dict (the
    shape ``monte_carlo_simulate`` returns under ``_phase_variances``)
    so callers can pass either without re-shaping.
    """
    if not phase_variances:
        return 0.0
    values = phase_variances.values() if isinstance(phase_variances, dict) else phase_variances
    return factor * math.sqrt(sum(values))


def add_business_days(start: date, days: float) -> date:
    """Add business days (skipping weekends) to a start date."""
    whole_days = int(days)
    current = start
    added = 0
    while added < whole_days:
        current += timedelta(days=1)
        if current.weekday() < 5:  # Mon-Fri
            added += 1
    return current
