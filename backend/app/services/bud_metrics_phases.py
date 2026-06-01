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

"""Per-phase metric derivation for the post-close Learning Agent.

Walks the BUD's status_change timeline to derive (entry → exit) windows
per phase, then cross-references the original BUDEstimateSnapshot to
compute actual-vs-estimated drift per phase. Returns the
``phase_metrics`` sub-dict that feeds the ``feature_learnings.metrics``
envelope.

Split out from ``bud_metrics`` so each file stays under the project's
~200-line cap and so contributor-counting work doesn't bloat the same
module that walks timestamps.
"""

import uuid
from datetime import datetime
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bud import BUDDocument, BUDStatus
from app.repositories.bud_estimate import BUDEstimateSnapshotRepository
from app.repositories.bud_timeline import BUDTimelineRepository

logger = structlog.get_logger(__name__)

# Phase keys the metrics envelope tracks. Ordered to match the canonical
# lifecycle so consumers (Learnings tab summary cards, the agent prompt,
# the rollup table) iterate in lifecycle order without re-sorting.
_TRACKED_PHASES: tuple[str, ...] = (
    BUDStatus.BUD.value,
    BUDStatus.DESIGN.value,
    BUDStatus.TECH_ARCH.value,
    BUDStatus.DEVELOPMENT.value,
    BUDStatus.CODE_REVIEW.value,
    BUDStatus.TESTING.value,
    BUDStatus.UAT.value,
    BUDStatus.PROD.value,
)


def _seconds_to_days(seconds: float) -> float:
    """Convert a ``timedelta.total_seconds()`` value to days (float)."""
    return round(seconds / 86_400.0, 3)


def _drift_pct(actual_days: float, estimated_days: float | None) -> float | None:
    """Percentage drift of actual vs estimate. Positive = overran the estimate.

    Returns None when no estimate exists or the estimate is zero (we
    can't meaningfully express drift against a baseline of 0).
    """
    if estimated_days is None or estimated_days <= 0:
        return None
    return round(((actual_days - estimated_days) / estimated_days) * 100.0, 1)


def _phase_windows_from_timeline(
    events: list[tuple[str, datetime]],
    bud_created_at: datetime,
    bud_closed_at: datetime,
) -> dict[str, tuple[datetime, datetime]]:
    """Derive (entry, exit) datetimes per phase from status_change events.

    The BUD starts in ``bud`` at ``created_at`` (implicit — no event is
    written for the initial assignment). Every subsequent status_change
    closes the prior phase's window and opens the next one. The final
    phase window closes at ``bud_closed_at``.
    """
    # v1 caveat: a BUD that bounces a phase (e.g. UAT → DEVELOPMENT →
    # UAT after a testing rejection) currently collapses the inner
    # round-trip into the outer window. The outer phase keeps its
    # original entry timestamp; the inner phase's two windows are
    # represented as one. We log a phase_reentered warning so the
    # signal is visible in observability, and leave the smarter
    # "sum disjoint windows" implementation for a follow-up once we
    # see real bouncing data in the wild.
    windows: dict[str, tuple[datetime, datetime]] = {}
    current_phase = BUDStatus.BUD.value
    current_entry = bud_created_at

    for to_phase, occurred_at in events:
        if to_phase == current_phase:
            continue  # Defensive: ignore no-op self-transitions
        # Close the current phase
        prior_entry, _ = windows.get(current_phase, (current_entry, current_entry))
        windows[current_phase] = (prior_entry, occurred_at)
        if to_phase in windows:
            logger.info(
                "phase_reentered_window_widened",
                phase=to_phase,
                reentered_at=occurred_at.isoformat(),
                note="actual_days will absorb the inner round-trip",
            )
        current_phase = to_phase
        current_entry = occurred_at

    # Final phase closes at bud_closed_at
    prior_entry, _ = windows.get(current_phase, (current_entry, current_entry))
    windows[current_phase] = (prior_entry, bud_closed_at)
    return windows


def _estimated_days_for_phase(
    phase: str,
    phase_estimates: dict[str, Any] | None,
) -> float | None:
    """Pull the original per-phase duration estimate (in days).

    ``BUDEstimateSnapshot.phase_estimates`` is the JSONB the estimator
    writes — each per-phase entry carries ``expected_days`` (the PERT-
    derived mean duration). ``p50_date / p70_date / p85_date`` are ISO
    date strings, not durations, and ``std_dev_days`` is a spread.
    ``expected_days`` is the only scalar that means "how long this phase
    was supposed to take" in the same units the actuals are reported in.

    The fallback aliases (``p70_days``, ``days``) survive in case a
    future estimator version emits the shape this helper originally
    expected — never matched today, kept so a contract change doesn't
    silently fall back to None.
    """
    if not phase_estimates:
        return None
    entry = phase_estimates.get(phase) or {}
    if not isinstance(entry, dict):
        return None
    # Prefer keys in priority order. A naive ``or`` chain skips 0.0
    # because Python treats it as falsy — but 0.0 is a legitimate
    # estimate ("this phase is instantaneous"), so we walk the keys
    # explicitly and take the first one that is present and non-null.
    raw: Any = None
    for key in ("expected_days", "p70_days", "days"):
        candidate = entry.get(key)
        if candidate is not None:
            raw = candidate
            break
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


async def build_phase_metrics(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud: BUDDocument,
    bud_closed_at: datetime,
) -> dict[str, dict[str, Any]]:
    """Return per-phase actual_days / estimated_days / drift_pct.

    Reads:
    - ``bud_timeline_events`` (status_change rows) for entry/exit times.
    - ``bud_estimate_snapshots`` (earliest row) for the original
      per-phase estimate.
    """
    timeline_repo = BUDTimelineRepository(db, org_id=org_id)
    status_events = await timeline_repo.list_for_bud_by_event_type(bud.id, "status_change")
    parsed: list[tuple[str, datetime]] = []
    for ev in status_events:
        detail = ev.detail or {}
        to_phase = detail.get("to") if isinstance(detail, dict) else None
        if isinstance(to_phase, str):
            parsed.append((to_phase, ev.created_at))

    snapshot_repo = BUDEstimateSnapshotRepository(db, org_id=org_id)
    earliest = await snapshot_repo.get_earliest_for_bud(bud.id)
    phase_estimates = earliest.phase_estimates if earliest else None

    windows = _phase_windows_from_timeline(parsed, bud.created_at, bud_closed_at)

    out: dict[str, dict[str, Any]] = {}
    for phase in _TRACKED_PHASES:
        window = windows.get(phase)
        if window is None:
            continue
        entry, exit_ = window
        actual_days = max(0.0, _seconds_to_days((exit_ - entry).total_seconds()))
        estimated_days = _estimated_days_for_phase(phase, phase_estimates)
        out[phase] = {
            "actual_days": actual_days,
            "estimated_days": estimated_days,
            "drift_pct": _drift_pct(actual_days, estimated_days),
            "entered_at": entry.isoformat(),
            "exited_at": exit_.isoformat(),
        }
    return out


def original_estimated_days_from_metrics(
    phase_metrics: dict[str, dict[str, Any]],
) -> float | None:
    """Sum the per-phase estimated_days, or None when no phase has an estimate."""
    total = 0.0
    seen = False
    for entry in phase_metrics.values():
        est = entry.get("estimated_days")
        if est is None:
            continue
        total += float(est)
        seen = True
    return round(total, 2) if seen else None
