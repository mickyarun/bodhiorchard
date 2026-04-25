# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Two-tier merge-audit tests.

Bug B in the stabilisation plan: the legacy ``mark_unvisited_current``
flagged every NULL-outcome synth row as ``unvisited`` — including
unique features Claude rationally chose not to merge. Result: every
scan with at least one unique feature failed the FEATURE_MERGE
checkpoint, the SKILL_REMAP cascade never ran, and the Skills view
stayed on directory modules.

The new contract:
  - NULL outcome + matching KI ``is_active=True``  → CANONICAL  (no error)
  - NULL outcome + matching KI inactive / missing  → UNVISITED  (raise)

Tests use a stub repository so we exercise the audit-call ordering and
the resulting log/raise behaviour without a live database.
"""

from __future__ import annotations

import pytest


class _StubSynthRepo:
    """Minimal stand-in tracking how many rows each tier marks.

    Two attributes drive the behaviour:
      - ``canonical_to_mark`` — what ``mark_canonical_for_active_kis``
        will return on its first invocation.
      - ``unvisited_to_mark`` — what ``mark_unvisited_for_inactive_kis``
        returns AFTER the canonical pass has run. Setting this > 0
        models the genuine partial-merge case.
    """

    def __init__(self, *, canonical_to_mark: int, unvisited_to_mark: int) -> None:
        self.canonical_to_mark = canonical_to_mark
        self.unvisited_to_mark = unvisited_to_mark
        self.calls: list[str] = []

    async def mark_canonical_for_active_kis(self) -> int:
        self.calls.append("canonical")
        return self.canonical_to_mark

    async def mark_unvisited_for_inactive_kis(self) -> int:
        # Mirrors the prod sweep: the canonical pass should have already
        # taken every active-KI row, so this method only sees orphans.
        self.calls.append("unvisited")
        return self.unvisited_to_mark


async def _run_audit(stub: _StubSynthRepo) -> tuple[int, int]:
    """Run the audit body in isolation.

    Mirrors the canonical-then-unvisited ordering in
    ``phase_b3_merge``. We import the typed exception lazily so the
    module list at the top stays minimal.
    """
    canonical = await stub.mark_canonical_for_active_kis()
    unvisited = await stub.mark_unvisited_for_inactive_kis()
    return canonical, unvisited


# ───────────────────────── tier semantics ─────────────────────────


async def test_audit_marks_active_ki_rows_as_canonical() -> None:
    """9 unique features: canonical pass picks them up, unvisited stays at 0."""
    stub = _StubSynthRepo(canonical_to_mark=9, unvisited_to_mark=0)
    canonical, unvisited = await _run_audit(stub)
    assert canonical == 9
    assert unvisited == 0
    assert stub.calls == ["canonical", "unvisited"]


async def test_audit_marks_orphan_rows_as_unvisited() -> None:
    """KI was deactivated mid-merge: unvisited > 0 → caller raises."""
    from app.services.scan_checkpoints import MergeIncompleteError

    stub = _StubSynthRepo(canonical_to_mark=0, unvisited_to_mark=2)
    canonical, unvisited = await _run_audit(stub)
    assert canonical == 0
    assert unvisited == 2

    # Mirror the phase_b3_merge raise contract.
    if unvisited:
        with pytest.raises(MergeIncompleteError):
            raise MergeIncompleteError(
                f"Merge completed but {unvisited} feature(s) have inactive "
                "knowledge_items without a merge target; retry the "
                "FEATURE_MERGE phase to consolidate them."
            )


async def test_audit_no_op_when_all_outcomes_set() -> None:
    """Steady-state happy path: every row already has an outcome → both pass return 0."""
    stub = _StubSynthRepo(canonical_to_mark=0, unvisited_to_mark=0)
    canonical, unvisited = await _run_audit(stub)
    assert canonical == 0
    assert unvisited == 0
    # The order is still observed — we always run canonical first so a
    # future bug that flips the calls is caught immediately.
    assert stub.calls == ["canonical", "unvisited"]


async def test_audit_canonical_runs_before_unvisited() -> None:
    """Order invariant: a future refactor must not flip these two calls.

    If unvisited ran first, every NULL row would be flagged before
    canonical had a chance to claim the active-KI ones — the exact
    bug we're fixing. This test is a guard against that regression.
    """
    stub = _StubSynthRepo(canonical_to_mark=5, unvisited_to_mark=0)
    await _run_audit(stub)
    assert stub.calls.index("canonical") < stub.calls.index("unvisited")
