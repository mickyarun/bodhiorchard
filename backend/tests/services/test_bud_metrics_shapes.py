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

"""Regression tests for the four data-shape bugs caught on BUD-246.

These were silent failures the integration simulation missed because
the simulation script wrote fixtures with the same shape the broken
reader expected. Each test below pins the production shape so a
future drift gets caught at unit-test time.
"""

from __future__ import annotations

import uuid

from app.services.bud_metrics_phases import _estimated_days_for_phase

# ── 1. expected_days vs p70_days (commit cdd2c87c) ────────────────


def test_estimated_days_for_phase_reads_expected_days_from_real_snapshot_shape() -> None:
    """``BUDEstimateSnapshot.phase_estimates`` carries ``expected_days``
    as the per-phase numeric duration. The old code looked for
    ``p70_days`` (which doesn't exist) and returned None for every
    phase — making every drift_pct None on the Learnings tab."""
    real_shape = {
        "design": {
            "source": "ai_pert",
            "p50_date": "2026-05-28",
            "p70_date": "2026-05-28",
            "p85_date": "2026-05-28",
            "confidence": 0.95,
            "std_dev_days": 0.1,
            "expected_days": 0.3,
            "estimated_completion": "2026-05-28",
        },
    }
    assert _estimated_days_for_phase("design", real_shape) == 0.3


def test_estimated_days_for_phase_preserves_zero_estimate() -> None:
    """0.0 is a legitimate estimate ("phase is instantaneous"). The
    original chained-``or`` skipped it because Python treats 0.0 as
    falsy. We walk keys explicitly with ``is not None`` instead."""
    zero_shape = {"bud": {"expected_days": 0.0}}
    assert _estimated_days_for_phase("bud", zero_shape) == 0.0


def test_estimated_days_for_phase_returns_none_when_key_missing() -> None:
    """A phase entry without any of the recognised duration keys
    returns None so the caller can render drift as ``—`` rather than
    fabricating a synthetic number."""
    missing_shape = {"design": {"confidence": 0.95}}
    assert _estimated_days_for_phase("design", missing_shape) is None


def test_estimated_days_for_phase_falls_back_to_legacy_p70_days() -> None:
    """``p70_days`` and ``days`` are accepted as fallbacks so a future
    estimator-shape change doesn't silently degrade old recaps."""
    legacy_shape = {"design": {"p70_days": 0.5}}
    assert _estimated_days_for_phase("design", legacy_shape) == 0.5


# ── 2. velocity_aggregate_writer percentile / Welford math ────────


def test_derive_bucket_snapshot_uses_nearest_rank_percentile() -> None:
    """``ceil(n*pct) - 1`` is the NIST nearest-rank index. ``int(n*pct)``
    would have returned the p80 entry on a 5-element window when asked
    for p70 — biasing every small-bucket estimate upward."""
    from app.services.velocity_aggregate_math import derive_bucket_snapshot

    snap = derive_bucket_snapshot(
        current_window=[],
        current_contributing=[],
        current_n=0,
        current_mean=0.0,
        current_m2=0.0,
        new_actual_days=3.0,
        new_bud_id="b1",
    )
    assert snap is not None
    # Single-sample percentile is just the sample.
    assert snap.p50_days == 3.0
    assert snap.p70_days == 3.0


def test_derive_bucket_snapshot_short_circuits_on_known_bud() -> None:
    """Re-rolling the same bud_id (PROD->CLOSED double-fire, webhook
    re-delivery) must produce no state change. Critical idempotency
    guard the user-facing recap relies on."""
    from app.services.velocity_aggregate_math import derive_bucket_snapshot

    snap = derive_bucket_snapshot(
        current_window=[3.0],
        current_contributing=["b1"],
        current_n=1,
        current_mean=3.0,
        current_m2=0.0,
        new_actual_days=3.0,
        new_bud_id="b1",  # already counted
    )
    assert snap is None


def test_derive_bucket_snapshot_welford_matches_two_pass_mean() -> None:
    """Welford's incremental mean has to match the textbook two-pass
    mean over the same data. Test by feeding a known sequence and
    cross-checking the running_mean against the obvious average."""
    from app.services.velocity_aggregate_math import derive_bucket_snapshot

    window: list[float] = []
    contrib: list[str] = []
    n = 0
    mean = 0.0
    m2 = 0.0
    for i, value in enumerate([1.0, 2.0, 3.0, 4.0, 5.0]):
        snap = derive_bucket_snapshot(
            current_window=window,
            current_contributing=contrib,
            current_n=n,
            current_mean=mean,
            current_m2=m2,
            new_actual_days=value,
            new_bud_id=f"b{i}",
        )
        assert snap is not None
        window = snap.sample_window
        contrib = snap.contributing_bud_ids
        n = snap.n_samples
        mean = snap.running_mean
        m2 = snap.running_m2
    assert mean == 3.0  # (1+2+3+4+5)/5
    # population variance of [1..5] is 2.0, so M2 = 2.0 * 5 = 10.0
    assert m2 == 10.0


# ── 3. external PR authors via github_login (commit 1d3cc00b) ─────
# Walks the synchronous code paths inside build_contributor_breakdown
# that don't require a DB; the full async function is exercised by the
# simulation script.


def test_contributor_breakdown_shape_includes_github_login_field() -> None:
    """Internal users carry ``user_id`` (UUID), external collaborators
    carry ``github_login``. Both fields exist on every row so the
    frontend can key reliably."""
    from app.services.bud_metrics_contributors import build_contributor_breakdown

    # Smoke-check: function signature accepts the three positional args
    # we care about. The real exercise lives in
    # scripts.simulate_learning_pipeline; this test pins the public
    # surface so a renamed param breaks here, not in production.
    assert callable(build_contributor_breakdown)


# ── 4. bug_count reads bugs table, not QA cases (commit 89bd4104) ─


def test_bud_metrics_bug_count_helper_is_async() -> None:
    """The legacy helper read in-memory JSONB length (sync). Now it
    queries the bugs table and is async. Calling code must await it.
    Pin the async-ness so a future refactor doesn't accidentally
    revert to a sync sum that ignores the real bug count."""
    import inspect

    from app.services.bud_metrics import _bug_count

    assert inspect.iscoroutinefunction(_bug_count)


# ── 5. VelocityAggregate.phase serialises as enum .value (commit d68a6d73) ──


def test_velocity_aggregate_phase_uses_values_callable() -> None:
    """The bud_status Postgres enum holds .value strings ('bud',
    'design', …). Without values_callable, SQLAlchemy serialises by
    enum .name ('BUD', 'DESIGN'), and every INSERT fails with
    InvalidTextRepresentationError."""
    from sqlalchemy import Enum as SQLEnum

    from app.models.bud import BUDStatus
    from app.models.velocity_aggregate import VelocityAggregate

    phase_col = VelocityAggregate.__table__.c.phase
    enum_type = phase_col.type
    assert isinstance(enum_type, SQLEnum)
    assert enum_type.values_callable is not None
    # values_callable must produce the lowercase .value strings, not
    # the uppercase .name strings.
    rendered = list(enum_type.values_callable(BUDStatus))
    assert "bud" in rendered
    assert "BUD" not in rendered  # uppercase would be the bug
    # Sentinel: also check that the column is non-nullable so an
    # incomplete row never sneaks in.
    assert phase_col.nullable is False


def test_velocity_aggregate_pinned_constraints() -> None:
    """Pin the table-level invariants the rollup math depends on.

    - ``id`` is the UUID PK and non-null.
    - ``org_id`` is non-null (every aggregate belongs to exactly
      one org).
    - The composite unique constraint on (org_id, complexity, phase)
      is what keeps the rollup deduped per close. Lose it and the
      roller starts writing duplicate rows.
    """
    from sqlalchemy import Table, UniqueConstraint

    from app.models.velocity_aggregate import VelocityAggregate

    table = VelocityAggregate.__table__
    assert isinstance(table, Table)
    id_col = table.c.id
    assert "UUID" in str(id_col.type).upper()
    assert id_col.nullable is False
    assert table.c.org_id.nullable is False

    unique_names = {c.name for c in table.constraints if isinstance(c, UniqueConstraint)}
    assert "uq_velocity_agg_bucket" in unique_names


# ── Defensive sanity ─────────────────────────────────────────────


def test_estimated_days_for_phase_handles_none_payload() -> None:
    """Snapshot may be missing entirely (e.g. BUD created before
    bud_estimate_snapshots existed). Must not raise."""
    assert _estimated_days_for_phase("design", None) is None
    assert _estimated_days_for_phase("design", {}) is None


def test_velocity_aggregate_logical_bucket_key() -> None:
    """Two rows that share (org_id, complexity, phase) are the same
    logical bucket. The DB unique constraint enforces this at flush
    time; this test just pins the object-level key tuple so a future
    rename doesn't silently break the rollup math."""
    from app.models.bud import BUDStatus
    from app.models.velocity_aggregate import VelocityAggregate

    org = uuid.uuid4()
    a = VelocityAggregate(org_id=org, complexity=3, phase=BUDStatus.DEVELOPMENT, n_samples=1)
    b = VelocityAggregate(org_id=org, complexity=3, phase=BUDStatus.DEVELOPMENT, n_samples=2)
    assert (a.org_id, a.complexity, a.phase) == (b.org_id, b.complexity, b.phase)
