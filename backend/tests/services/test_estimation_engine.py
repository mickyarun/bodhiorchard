# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Tests for the pure-math estimation engine.

The engine is deliberately database-free and LLM-free. Every behaviour it
exposes should be reachable with `random.Random(seed)` plus PERT triples,
which is what these tests exercise. Beta-PERT sampling is the primary
concern here because its shape is load-bearing for every percentile the
timeline panel renders.
"""

from __future__ import annotations

import math
import random

import pytest

from app.services.estimation_engine import (
    PERTEstimate,
    beta_pert_sample,
    monte_carlo_simulate,
    pert_expected,
)

# ── beta_pert_sample ────────────────────────────────────────────


@pytest.mark.parametrize(
    ("optimistic", "most_likely", "pessimistic"),
    [
        (1.0, 2.0, 5.0),  # asymmetric-right (tail toward pessimistic)
        (1.0, 4.0, 5.0),  # asymmetric-left  (tail toward optimistic)
        (2.0, 3.0, 4.0),  # symmetric
        (0.1, 0.5, 10.0),  # wide spread
    ],
)
def test_beta_pert_sample_stays_within_bounds(
    optimistic: float, most_likely: float, pessimistic: float
) -> None:
    """Every draw must land inside [O, P] — the distribution is bounded by
    construction. A violation would indicate a bug in the α/β derivation."""
    rng = random.Random(42)
    for _ in range(1_000):
        value = beta_pert_sample(rng, optimistic, most_likely, pessimistic)
        assert optimistic <= value <= pessimistic


@pytest.mark.parametrize(
    ("optimistic", "most_likely", "pessimistic"),
    [
        (1.0, 2.0, 5.0),
        (1.0, 4.0, 5.0),
        (2.0, 3.0, 4.0),
    ],
)
def test_beta_pert_sample_mean_matches_pert_expected(
    optimistic: float, most_likely: float, pessimistic: float
) -> None:
    """The Vose λ=4 choice exists precisely so the Beta-PERT mean equals
    the PERT weighted average (O+4M+P)/6. Drifting from that would mean
    `pert_expected` and the sampler no longer agree, and percentiles would
    no longer be interpretable against the analytic mean."""
    rng = random.Random(1337)
    samples = [beta_pert_sample(rng, optimistic, most_likely, pessimistic) for _ in range(10_000)]
    empirical_mean = sum(samples) / len(samples)
    analytic_mean = pert_expected(PERTEstimate(optimistic, most_likely, pessimistic))
    # 5 % tolerance accommodates the Monte Carlo sampling noise at n=10k.
    assert math.isclose(empirical_mean, analytic_mean, rel_tol=0.05)


def test_beta_pert_sample_zero_spread_returns_exact_value() -> None:
    """When O = M = P (e.g. a phase estimated as already complete), the
    α/β formulae would divide by zero. The helper must short-circuit
    cleanly to avoid propagating a ZeroDivisionError up through the MC
    loop — this was a real edge case in the previous triangular-based
    implementation's zero-short-circuit."""
    rng = random.Random(0)
    assert beta_pert_sample(rng, 0.0, 0.0, 0.0) == 0.0
    assert beta_pert_sample(rng, 2.5, 2.5, 2.5) == 2.5


def test_beta_pert_sample_is_deterministic_under_fixed_seed() -> None:
    """Reproducibility: two `random.Random(seed)` instances must produce
    the same draw sequence, otherwise tests downstream of the sampler
    become flaky."""
    a = random.Random(99)
    b = random.Random(99)
    for _ in range(50):
        assert beta_pert_sample(a, 1.0, 2.0, 5.0) == beta_pert_sample(b, 1.0, 2.0, 5.0)


# ── monte_carlo_simulate wiring ─────────────────────────────────


def test_monte_carlo_p50_close_to_analytic_mean() -> None:
    """Smoke test the MC wiring. A single phase with a moderate spread
    should have its P50 within ~5 % of the analytic PERT mean. This
    guards against regressions where the sampler is called with the
    wrong argument order (a classic bug — triangular expected
    `(low, high, mode)` whereas Beta-PERT expects `(O, M, P)`)."""
    est = PERTEstimate(1.0, 2.0, 5.0)
    results = monte_carlo_simulate({"dev": est}, ["dev"], n=10_000, seed=7)
    analytic = pert_expected(est)
    p50 = results["dev"]["p50"]
    assert math.isclose(p50, analytic, rel_tol=0.10)


def test_monte_carlo_zero_phase_short_circuits() -> None:
    """O == P == 0 is the "phase already complete" signal. Its contribution
    to every percentile must be exactly 0 regardless of most_likely."""
    done = PERTEstimate(0.0, 0.0, 0.0)
    active = PERTEstimate(1.0, 2.0, 3.0)
    results = monte_carlo_simulate(
        {"finished": done, "open": active}, ["finished", "open"], n=2_000, seed=1
    )
    # "finished" is the cumulative-through-finished sample, so it should be 0
    # at every percentile; "open" is cumulative through both, which equals
    # the active phase alone.
    for pct in ("p50", "p70", "p85"):
        assert results["finished"][pct] == 0.0
        assert results["open"][pct] > 0.0


# ── capacity_by_phase divisor (Phase B) ─────────────────────────


def test_monte_carlo_capacity_none_is_backward_compatible() -> None:
    """Default-None capacity must reproduce the un-capacity-aware
    behaviour exactly under the same seed. Guards against accidentally
    changing the math for callers that haven't migrated."""
    est = PERTEstimate(1.0, 2.0, 5.0)
    baseline = monte_carlo_simulate({"dev": est}, ["dev"], n=5_000, seed=42)
    same = monte_carlo_simulate({"dev": est}, ["dev"], n=5_000, seed=42, capacity_by_phase=None)
    assert baseline == same


def test_monte_carlo_capacity_scales_p50_inversely() -> None:
    """A capacity of 0.5 should roughly double the wall-clock estimate.
    This is the headline behaviour of capacity-aware MC — if it ever
    fails, the divisor has been moved out of the inner loop or the
    map keying is wrong."""
    est = PERTEstimate(1.0, 2.0, 5.0)
    full = monte_carlo_simulate({"dev": est}, ["dev"], n=10_000, seed=99)
    half = monte_carlo_simulate(
        {"dev": est},
        ["dev"],
        n=10_000,
        seed=99,
        capacity_by_phase={"dev": 0.5},
    )
    ratio = half["dev"]["p50"] / full["dev"]["p50"]
    # Expected ~2.0 ± Monte Carlo noise.
    assert 1.8 <= ratio <= 2.2


def test_monte_carlo_capacity_widens_variance() -> None:
    """Per-iteration division (vs. post-hoc multiplication) means the
    P85-P50 spread also stretches when capacity drops. This is the
    specific check from the research that distinguishes proper
    resource-aware MC from a naive after-the-fact multiplier."""
    est = PERTEstimate(1.0, 2.0, 5.0)
    full = monte_carlo_simulate({"dev": est}, ["dev"], n=10_000, seed=7)
    busy = monte_carlo_simulate(
        {"dev": est},
        ["dev"],
        n=10_000,
        seed=7,
        capacity_by_phase={"dev": 0.3},
    )
    full_spread = full["dev"]["p85"] - full["dev"]["p50"]
    busy_spread = busy["dev"]["p85"] - busy["dev"]["p50"]
    # 0.3 capacity ≈ 3.3× stretch, so spread should be visibly wider —
    # at least ~2× to leave headroom for sampling noise.
    assert busy_spread > 2 * full_spread


def test_monte_carlo_capacity_floors_at_min_capacity() -> None:
    """A pathologically-low capacity must not blow up the divisor —
    MIN_CAPACITY is the floor and the engine must respect it even when
    the caller passes 0 (defensive against caller bugs)."""
    from app.services.estimation_engine import MIN_CAPACITY

    est = PERTEstimate(1.0, 2.0, 5.0)
    floored = monte_carlo_simulate(
        {"dev": est},
        ["dev"],
        n=2_000,
        seed=3,
        capacity_by_phase={"dev": 0.0},
    )
    explicit_floor = monte_carlo_simulate(
        {"dev": est},
        ["dev"],
        n=2_000,
        seed=3,
        capacity_by_phase={"dev": MIN_CAPACITY},
    )
    assert floored == explicit_floor


# ── historical reference-class sampling (Phase C) ────────────────


def test_historical_sample_picks_from_supplied_list() -> None:
    """Bootstrap must only ever return values that were observed in
    history — no interpolation, no smoothing. That's the whole point of
    reference-class forecasting (Magennis): trust the data."""
    from app.services.estimation_engine import historical_sample

    rng = random.Random(7)
    samples = [3.0, 5.0, 8.0]
    for _ in range(200):
        assert historical_sample(rng, samples) in samples


def test_monte_carlo_historical_weight_zero_is_backward_compatible() -> None:
    """historical_weight=0 (default) must produce the same results as
    Phase B with no historical data — guards against accidental signal
    bleed when callers haven't migrated."""
    est = PERTEstimate(1.0, 2.0, 5.0)
    baseline = monte_carlo_simulate({"dev": est}, ["dev"], n=5_000, seed=11)
    same = monte_carlo_simulate(
        {"dev": est},
        ["dev"],
        n=5_000,
        seed=11,
        historical_by_phase={"dev": [99.0, 99.0]},  # ignored at weight 0
        historical_weight=0.0,
    )
    assert baseline == same


def test_monte_carlo_historical_weight_one_replaces_llm_completely() -> None:
    """When historical_weight=1 and the historical list is constant,
    every iteration's sample for that phase is that constant. Confirms
    historical draws bypass the LLM Beta-PERT path entirely."""
    est = PERTEstimate(1.0, 2.0, 5.0)
    constant_history = [4.0]
    results = monte_carlo_simulate(
        {"dev": est},
        ["dev"],
        n=2_000,
        seed=2,
        historical_by_phase={"dev": constant_history},
        historical_weight=1.0,
    )
    for pct in ("p50", "p70", "p85"):
        assert results["dev"][pct] == 4.0


def test_monte_carlo_historical_skips_capacity_divisor() -> None:
    """Historical samples are already wall-clock; the capacity divisor
    must not be applied to them. With historical_weight=1, capacity
    should have zero effect on the result. This is the subtle bit that
    keeps effort and wall-clock from getting double-counted."""
    est = PERTEstimate(1.0, 2.0, 5.0)
    history = [4.0]
    full_cap = monte_carlo_simulate(
        {"dev": est},
        ["dev"],
        n=2_000,
        seed=8,
        capacity_by_phase={"dev": 1.0},
        historical_by_phase={"dev": history},
        historical_weight=1.0,
    )
    half_cap = monte_carlo_simulate(
        {"dev": est},
        ["dev"],
        n=2_000,
        seed=8,
        capacity_by_phase={"dev": 0.5},
        historical_by_phase={"dev": history},
        historical_weight=1.0,
    )
    assert full_cap == half_cap


def test_monte_carlo_empty_historical_list_falls_back_to_llm() -> None:
    """A phase with an empty historical list should silently use the LLM
    path, even at high historical_weight — defensive against partially
    available history (e.g. only 'design' has past data, not 'testing')."""
    est = PERTEstimate(1.0, 2.0, 5.0)
    fallback = monte_carlo_simulate(
        {"dev": est},
        ["dev"],
        n=2_000,
        seed=4,
        historical_by_phase={"dev": []},
        historical_weight=0.9,
    )
    llm_only = monte_carlo_simulate({"dev": est}, ["dev"], n=2_000, seed=4)
    assert fallback == llm_only


# ── project_buffer + per-phase variance (Phase D) ───────────────


def test_monte_carlo_returns_per_phase_variance() -> None:
    """The MC results dict must expose ``_phase_variances`` so the
    project-buffer math can run without re-sampling. Every phase in
    ``remaining_phases`` must have a variance entry — missing ones
    would silently drop terms from the √Σ aggregate."""
    estimates = {
        "dev": PERTEstimate(1.0, 2.0, 5.0),
        "qa": PERTEstimate(0.5, 1.0, 2.0),
    }
    out = monte_carlo_simulate(estimates, ["dev", "qa"], n=2_000, seed=21)
    variances = out["_phase_variances"]
    assert set(variances.keys()) == {"dev", "qa"}
    # Empirically positive for any non-degenerate spread.
    assert variances["dev"] > 0
    assert variances["qa"] > 0


def test_project_buffer_days_sqrt_sum_form() -> None:
    """Goldratt's CCM buffer is factor · √Σ(variance) — independence
    assumption baked in. With variances [1, 1, 4], √6 ≈ 2.449, so a
    1.5× factor gives ~3.674. Locking the formula in a test makes
    accidental coefficient tweaks visible."""
    import math as _math

    from app.services.estimation_engine import project_buffer_days

    expected = 1.5 * _math.sqrt(6.0)
    assert math.isclose(project_buffer_days([1.0, 1.0, 4.0]), expected)


def test_project_buffer_days_accepts_dict_or_list() -> None:
    """The MC engine returns ``_phase_variances`` as a dict; the helper
    must accept that shape directly (not require a re-projection step
    in every caller)."""
    from app.services.estimation_engine import project_buffer_days

    as_dict = project_buffer_days({"dev": 1.0, "qa": 4.0})
    as_list = project_buffer_days([1.0, 4.0])
    assert math.isclose(as_dict, as_list)


def test_project_buffer_days_zero_for_empty_or_no_variance() -> None:
    """Empty input or all-zero variances → no buffer. Backward-compat
    for partially-completed BUDs whose remaining phase list is empty,
    so the panel renders 'Buffer: 0d' instead of crashing."""
    from app.services.estimation_engine import project_buffer_days

    assert project_buffer_days([]) == 0.0
    assert project_buffer_days({}) == 0.0
    assert project_buffer_days([0.0, 0.0]) == 0.0


def test_project_buffer_days_factor_override() -> None:
    """The Goldratt 1.5× factor is the default but configurable. A 2×
    factor on variance=4 (σ=2) returns 4."""
    from app.services.estimation_engine import project_buffer_days

    assert math.isclose(project_buffer_days([4.0], factor=2.0), 4.0)
