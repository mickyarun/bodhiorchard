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

"""Tests for estimation context helpers.

Covers:
- ``compute_bud_complexity`` — pure derivation (bug-bump + base heuristic).
- ``get_bug_context`` — open-bug aggregate query shape.
- ``get_historical_phase_durations`` — complexity-bucket reference class
  and proportional cycle-time split.

The DB-backed helpers use an ``AsyncMock`` session so the behaviour can
be pinned without spinning up Postgres; whole-DB integration paths are
covered separately by the integration suite.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.estimation_context import (
    BUG_COMPLEXITY_BUCKET,
    compute_bud_complexity,
    get_bug_context,
    get_historical_phase_durations,
)


def _stub_bud(
    requirements_md: str = "## PRD\nshort.",
    tech_spec_md: str = "",
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        requirements_md=requirements_md,
        tech_spec_md=tech_spec_md,
        impacted_repos=[],
        qa_automation_cases=[],
        qa_manual_cases=[],
    )


# ─── compute_bud_complexity ──────────────────────────────────────────────


def test_complexity_baseline_with_no_bugs_unchanged() -> None:
    """The default ``open_bug_count=0`` keeps existing callers
    behaviour-stable — no surprise bumps when bugs aren't supplied."""
    assert compute_bud_complexity(_stub_bud()) >= 1


def test_complexity_bumps_one_per_bucket_of_open_bugs() -> None:
    """Bugs are *more work*, so they belong on the complexity axis. A
    full bucket bumps complexity by one; a partial bucket does not."""
    bud = _stub_bud()
    base = compute_bud_complexity(bud, open_bug_count=0)
    one_bucket = compute_bud_complexity(bud, open_bug_count=BUG_COMPLEXITY_BUCKET)
    two_buckets = compute_bud_complexity(bud, open_bug_count=2 * BUG_COMPLEXITY_BUCKET)
    assert one_bucket == min(5, base + 1)
    assert two_buckets == min(5, base + 2)


def test_complexity_partial_bucket_does_not_bump() -> None:
    bud = _stub_bud()
    base = compute_bud_complexity(bud, open_bug_count=0)
    almost_full = compute_bud_complexity(bud, open_bug_count=BUG_COMPLEXITY_BUCKET - 1)
    assert almost_full == base


def test_complexity_caps_at_five_even_with_many_bugs() -> None:
    """The 1-5 scale is load-bearing — overshooting it would break the
    calibration table in the prompt and the heuristic-fallback spread."""
    bud = _stub_bud()
    capped = compute_bud_complexity(bud, open_bug_count=100)
    assert capped == 5


# ─── Async helpers (mock-based) ──────────────────────────────────────────
#
# Each helper issues a single ``await db.execute(...)`` — we mock the
# session and pin the shape of the result (scalar_one / scalars().all())
# to match SQLAlchemy 2.0's async result API.


def _scalar_result(value: int | None) -> MagicMock:
    """Fake ``Result`` whose ``scalar_one()`` returns the given value."""
    result = MagicMock()
    result.scalar_one = MagicMock(return_value=value)
    return result


def _rows_result(rows: list[object]) -> MagicMock:
    """Fake ``Result`` whose ``scalars().all()`` returns the given rows."""
    result = MagicMock()
    scalars = MagicMock()
    scalars.all = MagicMock(return_value=rows)
    result.scalars = MagicMock(return_value=scalars)
    return result


# ─── get_bug_context ─────────────────────────────────────────────────────


async def test_bug_context_returns_open_bug_count() -> None:
    """The helper shape is a dict so future fields (severity, module)
    slot in without touching callers."""
    db = AsyncMock()
    db.execute.return_value = _scalar_result(3)
    result = await get_bug_context(db, uuid.uuid4(), _stub_bud())
    assert result == {"open_bug_count": 3}


async def test_bug_context_zero_when_no_open_bugs() -> None:
    db = AsyncMock()
    db.execute.return_value = _scalar_result(0)
    result = await get_bug_context(db, uuid.uuid4(), _stub_bud())
    assert result == {"open_bug_count": 0}


# ─── get_historical_phase_durations ──────────────────────────────────────


def _completed_bud(days: int) -> SimpleNamespace:
    """Stand-in BUDDocument with a known cycle length for bootstrap math."""
    now = datetime.now(UTC)
    return SimpleNamespace(
        created_at=now - timedelta(days=days),
        updated_at=now,
    )


def _stub_aggregate(
    phase_value: str,
    sample_window: list[float],
    *,
    n_samples: int | None = None,
) -> SimpleNamespace:
    """Stand-in VelocityAggregate row with just the fields the helper reads."""
    from app.models.bud import BUDStatus

    return SimpleNamespace(
        phase=BUDStatus(phase_value),
        sample_window=sample_window,
        n_samples=n_samples if n_samples is not None else len(sample_window),
    )


def _two_call_mock(first: list[object], second: list[object]) -> AsyncMock:
    """AsyncMock whose ``execute`` returns ``first`` then ``second``.

    Mirrors the helper's two-query shape: velocity_aggregates lookup
    first, then the legacy completed-BUDs lookup as fallback.
    """
    db = AsyncMock()
    db.execute.side_effect = [_rows_result(first), _rows_result(second)]
    return db


async def test_historical_empty_when_neither_aggregates_nor_completed_buds() -> None:
    """Empty rollup + empty legacy bucket → empty result. Caller falls
    back to LLM-only (zero historical_weight), the invariant the engine
    relies on."""
    db = _two_call_mock([], [])
    result = await get_historical_phase_durations(
        db, uuid.uuid4(), target_complexity=3, phase_order=["development", "testing"]
    )
    assert result == {}


async def test_historical_reads_aggregates_when_enough_samples() -> None:
    """A bucket with >= MIN_SAMPLES_FOR_TRUSTED real samples bypasses the
    proportional split and emits the per-BUD sample window directly so
    the Monte Carlo loop bootstraps over the real distribution."""
    samples = [2.0, 3.0, 4.0, 5.0, 6.0]
    db = _two_call_mock([_stub_aggregate("development", samples)], [])
    result = await get_historical_phase_durations(
        db, uuid.uuid4(), target_complexity=3, phase_order=["development"]
    )
    assert result["development"] == pytest.approx(samples)


async def test_historical_tops_up_from_legacy_when_aggregates_short() -> None:
    """A bucket with too few samples must NOT silently override the
    proportional split — the rollup is informative only once it has
    enough data to beat the default. The two paths are additive: short
    rollups top up with the legacy split rather than replace it."""
    short = _stub_aggregate("development", [1.0, 2.0], n_samples=2)
    completed = [_completed_bud(days=10)]
    db = _two_call_mock([short], completed)
    result = await get_historical_phase_durations(
        db, uuid.uuid4(), target_complexity=3, phase_order=["development"]
    )
    # Should NOT contain the rollup's [1.0, 2.0] (n_samples below threshold);
    # only the legacy proportional sample lands in the result.
    assert 1.0 not in result["development"]
    assert 2.0 not in result["development"]
    assert len(result["development"]) == 1  # one completed BUD → one proportional sample


async def test_historical_splits_cycle_proportionally_by_default_phase_share() -> None:
    """Each phase's duration is its share of ``DEFAULT_PHASE_DAYS``
    times the observed whole-BUD cycle — the Magennis bootstrap shape
    (still applied when the rollup is empty)."""
    from app.services.estimation_engine import DEFAULT_PHASE_DAYS

    db = _two_call_mock([], [_completed_bud(days=10)])
    phases = ["development", "testing"]
    result = await get_historical_phase_durations(
        db, uuid.uuid4(), target_complexity=3, phase_order=phases
    )

    total = sum(DEFAULT_PHASE_DAYS[p] for p in phases)
    assert set(result.keys()) == set(phases)
    assert result["development"] == pytest.approx(
        [10.0 * DEFAULT_PHASE_DAYS["development"] / total]
    )
    assert result["testing"] == pytest.approx([10.0 * DEFAULT_PHASE_DAYS["testing"] / total])


async def test_historical_clamps_zero_day_cycle_to_one() -> None:
    """Same-day create-and-close BUDs would otherwise emit 0-day samples
    and pull the bootstrap mean toward zero. The min-1-day clamp is the
    stated invariant in the helper's docstring."""
    db = _two_call_mock([], [_completed_bud(days=0)])
    result = await get_historical_phase_durations(
        db, uuid.uuid4(), target_complexity=3, phase_order=["development"]
    )
    assert result["development"] == pytest.approx([1.0])


async def test_historical_aggregates_multiple_buds() -> None:
    """Every matching legacy-bucket BUD contributes one sample per phase;
    the engine consumes these as a distribution, not an average, so
    order / count across samples must be preserved."""
    db = _two_call_mock(
        [],
        [_completed_bud(days=4), _completed_bud(days=8), _completed_bud(days=12)],
    )
    result = await get_historical_phase_durations(
        db, uuid.uuid4(), target_complexity=3, phase_order=["development"]
    )
    assert len(result["development"]) == 3


async def test_historical_ignores_phases_absent_from_default_map() -> None:
    """The proportional split uses DEFAULT_PHASE_DAYS; a phase the engine
    doesn't know about must not leak into the result (it would divide by
    an inflated total and skew every other phase)."""
    db = _two_call_mock([], [_completed_bud(days=10)])
    result = await get_historical_phase_durations(
        db, uuid.uuid4(), target_complexity=3, phase_order=["development", "not_a_real_phase"]
    )
    assert "not_a_real_phase" not in result
    assert "development" in result


async def test_historical_handles_extreme_complexity_targets() -> None:
    """Bucket edges at complexity 1 and 5 must not produce out-of-range
    bounds (the SQL BETWEEN would fail) — the helper clamps via max/min."""
    low_db = _two_call_mock([], [])
    high_db = _two_call_mock([], [])
    low = await get_historical_phase_durations(low_db, uuid.uuid4(), 1, ["development"])
    high = await get_historical_phase_durations(high_db, uuid.uuid4(), 5, ["development"])
    assert low == {} and high == {}
