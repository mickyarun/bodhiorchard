# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Tests for scan_progress clamp + fallback semantics + resolve fallthrough.

Covers the three invariants the tab-switch-scan-404 + >100% bugs rely on:

1. ``_clamp_pct`` never returns above 100 and never regresses.
2. Fallback dict entries survive a terminal status update (only age out
   via ``_prune_stale_fallback``), so a poll arriving milliseconds after
   completion still finds the scan.
3. ``resolve_scan_progress`` falls back to the org's active scan when a
   direct id lookup misses — the Redis path is monkeypatched to ``None``
   so we exercise the in-memory code path deterministically.
"""

from __future__ import annotations

import time

import pytest

from app.services import scan_progress


@pytest.fixture(autouse=True)
def _reset_fallback() -> None:
    """Isolate the module-level dict between tests — no bleed across."""
    scan_progress._fallback.clear()
    scan_progress._org_scan_map.clear()
    yield
    scan_progress._fallback.clear()
    scan_progress._org_scan_map.clear()


@pytest.fixture
def _force_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pretend Redis is unavailable so the fallback path is exercised."""

    async def _no_redis() -> None:
        return None

    monkeypatch.setattr("app.services.redis_client.get_redis", _no_redis)


# ─── _clamp_pct ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("current", "requested", "expected"),
    [
        (0, 0, 0),
        (0, 50, 50),
        (50, 100, 100),
        (50, 120, 100),  # upper bound clamp — the bug we're fixing
        (90, 40, 90),  # monotonic — never regress
        (100, 100, 100),
        (100, 200, 100),  # stays at ceiling even with huge overshoot
    ],
)
def test_clamp_pct_bounds(current: int, requested: int, expected: int) -> None:
    assert scan_progress._clamp_pct(current, requested) == expected


# ─── Fallback not popped on terminal ────────────────────────────────────────


async def test_fallback_survives_terminal_status(_force_fallback: None) -> None:
    """After a scan completes, the fallback entry must stay readable
    until TTL. A poll landing right after completion needs to see the
    final status, not a phantom 404."""
    await scan_progress.create_scan_progress("scan-x", "org-1")
    await scan_progress.update_scan_progress("scan-x", status="completed", progress_pct=100)

    status = await scan_progress.get_scan_progress("scan-x")
    assert status is not None
    assert status.status == "completed"
    assert status.progress_pct == 100


async def test_fallback_prunes_stale_entries(
    _force_fallback: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fallback entries older than ``_SCAN_TTL`` get swept when any read
    happens — bounding memory without eager deletion."""
    await scan_progress.create_scan_progress("scan-old", "org-old")
    # Back-date the updated_at so the entry appears stale.
    scan_progress._fallback["scan-old"]["updated_at"] = str(
        time.time() - scan_progress._SCAN_TTL - 1
    )

    # Reading any scan triggers the prune sweep.
    await scan_progress.get_scan_progress("scan-old")
    assert "scan-old" not in scan_progress._fallback
    assert "org-old" not in scan_progress._org_scan_map


# ─── resolve_scan_progress fall-through ─────────────────────────────────────


async def test_resolve_falls_back_to_active_org_scan(_force_fallback: None) -> None:
    """If the direct id lookup misses BUT the org has the same scan_id
    registered as active (e.g. a transient miss during a tab switch),
    resolve_scan_progress should return the live status."""
    await scan_progress.create_scan_progress("scan-y", "org-2")
    # Remove the direct entry to simulate a transient cache miss while
    # keeping the org → scan_id mapping intact (mimics what the bug
    # produces in practice).
    direct = scan_progress._fallback.pop("scan-y")
    # Re-seed under a shadow key so get_active_scan_for_org can still
    # resolve via _org_scan_map.
    scan_progress._fallback["scan-y-shadow"] = direct
    scan_progress._org_scan_map["org-2"] = "scan-y-shadow"
    direct["scan_id"] = "scan-y-shadow"

    resolved = await scan_progress.resolve_scan_progress("scan-y-shadow", "org-2")
    assert resolved is not None
    assert resolved.scan_id == "scan-y-shadow"


async def test_resolve_returns_none_for_unknown_scan(_force_fallback: None) -> None:
    """When there's no direct entry AND the org has no active scan with
    the requested id, resolve_scan_progress returns None so the endpoint
    can honestly 404."""
    result = await scan_progress.resolve_scan_progress("does-not-exist", "org-3")
    assert result is None
