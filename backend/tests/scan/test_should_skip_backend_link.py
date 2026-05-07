# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Unit tests for the global ``backend_link`` skip predicate.

The predicate's contract: skip the linker iff zero per-repo
``FEATURE_SYNTHESIS`` or ``EXTRACT_ROUTES`` step rows reached ``DONE``
in this scan. These tests stub the underlying repository helper so the
decision logic is exercised without DB scaffolding.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from app.models.scan_phase import ScanPhase
from app.services.scan.stages import _skip_predicates as predicates


async def _patch_has_done(monkeypatch: pytest.MonkeyPatch, *, has_done: bool) -> None:
    """Replace ``has_done_step_for_scan`` with a deterministic stub."""

    async def _stub(_db: Any, **_kw: Any) -> bool:
        return has_done

    monkeypatch.setattr(predicates, "has_done_step_for_scan", _stub)


async def test_skip_when_no_done_steps(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every per-repo phase SKIPPED_CACHE / absent → linker skips."""
    await _patch_has_done(monkeypatch, has_done=False)
    decision = await predicates.should_skip_backend_link(
        db=None,  # type: ignore[arg-type]
        org_id=uuid.uuid4(),
        scan_id=uuid.uuid4(),
    )
    assert decision.skip is True
    assert decision.reason is not None
    assert "unchanged" in decision.reason


async def test_runs_when_at_least_one_done_step(monkeypatch: pytest.MonkeyPatch) -> None:
    """Any DONE step (frontend synth OR backend extract) → linker runs."""
    await _patch_has_done(monkeypatch, has_done=True)
    decision = await predicates.should_skip_backend_link(
        db=None,  # type: ignore[arg-type]
        org_id=uuid.uuid4(),
        scan_id=uuid.uuid4(),
    )
    assert decision.skip is False
    assert decision.reason is not None
    assert "DONE" in decision.reason


async def test_predicate_failsafe_on_db_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """A DB error must NOT skip — the linker is idempotent and re-running
    when nothing changed is wasted I/O but never wrong; silently skipping
    on a query failure could hide a real input-state regression.
    """

    async def _boom(_db: Any, **_kw: Any) -> bool:
        raise RuntimeError("connection reset")

    monkeypatch.setattr(predicates, "has_done_step_for_scan", _boom)
    decision = await predicates.should_skip_backend_link(
        db=None,  # type: ignore[arg-type]
        org_id=uuid.uuid4(),
        scan_id=uuid.uuid4(),
    )
    assert decision.skip is False
    assert decision.reason == "predicate_error: backend_link"


async def test_predicate_queries_correct_phase_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """The predicate must pass exactly FEATURE_SYNTHESIS and EXTRACT_ROUTES.

    Adding a new gating phase later is expected — this test pins the
    current set so an accidental rename or omission is caught.
    """
    captured: dict[str, Any] = {}

    async def _capture(_db: Any, **kw: Any) -> bool:
        captured.update(kw)
        return False

    monkeypatch.setattr(predicates, "has_done_step_for_scan", _capture)
    await predicates.should_skip_backend_link(
        db=None,  # type: ignore[arg-type]
        org_id=uuid.uuid4(),
        scan_id=uuid.uuid4(),
    )
    # Order is irrelevant to the SQL — the underlying `.in_()` clause is
    # set-semantics. Compare as a set so a future rearrange doesn't break.
    assert set(captured["phases"]) == {
        ScanPhase.FEATURE_SYNTHESIS,
        ScanPhase.EXTRACT_ROUTES,
    }
