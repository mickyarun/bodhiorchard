"""Pure computation engine for PERT and Monte Carlo estimation.

No database access, no LLM calls — just math. This keeps the estimation
logic testable and deterministic (seed-able for reproducible tests).
"""

import random
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


def default_pert_spread(
    complexity: int,
    backlog_depth: int,
    assignee_workload: int,
) -> dict[str, PERTEstimate]:
    """Generate conservative PERT spreads from defaults when LLM is unavailable.

    Scales base durations by complexity (1-5), backlog depth, and workload.
    """
    complexity_factor = complexity / 3.0
    queue_factor = 1 + (backlog_depth * 0.3)
    workload_factor = 1 + (assignee_workload * 0.2)
    combined = queue_factor * workload_factor

    result: dict[str, PERTEstimate] = {}
    for phase, base in DEFAULT_PHASE_DAYS.items():
        scaled = base * complexity_factor * combined
        result[phase] = PERTEstimate(
            optimistic=round(scaled * 0.6, 1),
            most_likely=round(scaled, 1),
            pessimistic=round(scaled * 2.0, 1),
        )
    return result


def monte_carlo_simulate(
    pert_estimates: dict[str, PERTEstimate],
    remaining_phases: list[str],
    n: int = 10_000,
    seed: int | None = None,
) -> dict[str, dict[str, float]]:
    """Run Monte Carlo simulation over PERT estimates.

    Returns per-phase and cumulative percentile results (p50, p70, p85)
    in business days from today.
    """
    rng = random.Random(seed)
    phase_samples: dict[str, list[float]] = {p: [] for p in remaining_phases}
    cumulative_samples: list[float] = []

    for _ in range(n):
        total = 0.0
        for phase in remaining_phases:
            est = pert_estimates[phase]
            if est.optimistic == est.pessimistic == 0:
                sampled = 0.0
            else:
                sampled = rng.triangular(est.optimistic, est.pessimistic, est.most_likely)
            phase_samples[phase].append(total + sampled)
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
    return result


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


def compute_complexity(
    requirements_len: int,
    tech_spec_len: int,
    impacted_repo_count: int,
    qa_case_count: int,
) -> int:
    """Derive a 1-5 complexity score from BUD signals.

    Weights repo count and QA cases heavily (actual scope indicators).
    Content length is a weak signal — AI agents write verbose specs
    even for simple features, so thresholds are high.
    """
    score = 1.0

    # Content volume — weak signal, high thresholds
    content_len = requirements_len + tech_spec_len
    if content_len > 30000:
        score += 1.0
    elif content_len > 15000:
        score += 0.5

    # Multi-repo is a strong complexity signal
    if impacted_repo_count >= 4:
        score += 2.0
    elif impacted_repo_count >= 3:
        score += 1.5
    elif impacted_repo_count >= 2:
        score += 0.5

    # QA case volume — strong signal for testing complexity
    if qa_case_count > 20:
        score += 1.5
    elif qa_case_count > 10:
        score += 1.0
    elif qa_case_count > 5:
        score += 0.5

    return max(1, min(5, round(score)))
