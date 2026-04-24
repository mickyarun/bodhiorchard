# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Progress-budget invariant tests for the scan pipeline.

Guards against the "progress > 100%" regression that arose when the
per-repo ``base_pct`` schedule overflowed the repo-phase window as the
number of repos grew. The tests:

1. Fix the ``_repo_base_pct`` function: for any N, the last repo's
   maximum possible pct (``base_pct + PER_REPO_OFFSET_MAX``) must stay
   within ``REPO_WINDOW_END``.
2. Scan the scan_pipeline + scan_phases source files for every
   ``base_pct + <int>`` literal and assert the biggest one is ≤
   ``PER_REPO_OFFSET_MAX`` — if a future phase adds a bigger offset,
   this test fires instead of silently overflowing in production.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.services import scan_pipeline


@pytest.mark.parametrize("total_repos", [1, 2, 5, 10, 20, 50])
def test_last_repo_stays_within_window(total_repos: int) -> None:
    """The invariant the whole scheme relies on."""
    last_base = scan_pipeline._repo_base_pct(total_repos - 1, total_repos)
    assert last_base + scan_pipeline.PER_REPO_OFFSET_MAX <= scan_pipeline.REPO_WINDOW_END


@pytest.mark.parametrize("total_repos", [1, 2, 5, 20])
def test_base_pct_monotonic(total_repos: int) -> None:
    """base_pct is non-decreasing across repo_idx so the progress bar
    moves forward as the loop advances."""
    seq = [scan_pipeline._repo_base_pct(i, total_repos) for i in range(total_repos)]
    assert seq == sorted(seq), seq


def test_single_repo_starts_at_window_start() -> None:
    """For N=1 the repo has no predecessors, so base_pct should equal
    the window start (no wasted budget)."""
    assert scan_pipeline._repo_base_pct(0, 1) == scan_pipeline.REPO_WINDOW_START


# ─── Drift guard: every "base_pct + N" literal stays ≤ PER_REPO_OFFSET_MAX ──


_OFFSET_RE = re.compile(r"base_pct\s*\+\s*(\d+)")
_SOURCE_FILES = ("scan_pipeline.py", "scan_phases.py")


def test_no_per_repo_offset_literal_exceeds_max() -> None:
    """If a new phase later adds ``base_pct + 99``, this test catches it
    so the offset-max constant can be bumped in lockstep instead of the
    UI silently showing > 100%."""
    services = Path(scan_pipeline.__file__).parent
    biggest = 0
    for name in _SOURCE_FILES:
        text = (services / name).read_text()
        for literal in _OFFSET_RE.findall(text):
            biggest = max(biggest, int(literal))
    assert biggest <= scan_pipeline.PER_REPO_OFFSET_MAX, (
        f"Found base_pct + {biggest} but PER_REPO_OFFSET_MAX is "
        f"{scan_pipeline.PER_REPO_OFFSET_MAX}. Either shrink the offset "
        f"or bump the constant (and widen REPO_WINDOW_END if needed)."
    )
