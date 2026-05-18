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

"""Pure-function checks on the narrow-synth smoke harness.

Covers the log-tail scanner — the assertion engine of the harness — in
isolation from anything that needs a real backend, DB seeding, or
subprocess invocation. The full E2E flow is exercised manually against
a running backend; these tests just prove the scanner won't lie when
it does run.

Three properties exercised:

1. Markers present in the tail (after a captured baseline offset)
   are reported as found.
2. Markers that exist only *before* the baseline offset are NOT
   reported — the scanner must scope to the tail this run produced,
   not to the whole log file's history.
3. Log rotation between baseline capture and scan time is recovered
   from gracefully: a smaller post-rotation file gets scanned from
   the start instead of seeking past EOF.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_harness():  # type: ignore[no-untyped-def]
    """Import the harness as a module (it lives under ``backend/scripts``)."""
    here = Path(__file__).resolve().parent.parent.parent  # backend/
    spec = importlib.util.spec_from_file_location(
        "narrow_synth_harness",
        str(here / "scripts" / "smoke_narrow_synth.py"),
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_scanner_finds_markers_in_tail(tmp_path: Path) -> None:
    """Markers in the post-baseline tail are reported."""
    harness = _load_harness()
    log = tmp_path / "bodhi.log"
    log.write_text("pre-baseline old garbage\n")
    baseline = harness._log_size(str(log))
    log.write_text(
        "pre-baseline old garbage\n"
        "[info] pr_merge_update_clusters_affected affected_count=1\n"
        "[info] job_created job_type=pr_narrow_synthesis worker=1\n"
    )
    found = harness._scan_log_tail(
        log_path=str(log),
        from_offset=baseline,
        markers=["pr_merge_update_clusters_affected", "pr_narrow_synthesis"],
    )
    assert found == {"pr_merge_update_clusters_affected", "pr_narrow_synthesis"}


def test_scanner_ignores_markers_before_baseline(tmp_path: Path) -> None:
    """Markers older than this run's baseline must not be reported.

    Critical: a marker from yesterday's run sitting in the same log
    file should NOT register a PASS on a fresh run that didn't
    actually trigger anything.
    """
    harness = _load_harness()
    log = tmp_path / "bodhi.log"
    log.write_text(
        "[info] pr_merge_update_clusters_affected affected_count=1 (OLD)\n"
        "[info] job_created job_type=pr_narrow_synthesis (OLD)\n"
    )
    baseline = harness._log_size(str(log))
    # No new content this run.
    found = harness._scan_log_tail(
        log_path=str(log),
        from_offset=baseline,
        markers=["pr_merge_update_clusters_affected", "pr_narrow_synthesis"],
    )
    assert found == set()


def test_scanner_recovers_from_log_rotation(tmp_path: Path) -> None:
    """If the file got smaller (rotated), scan from byte 0 of the new file."""
    harness = _load_harness()
    log = tmp_path / "bodhi.log"
    log.write_text("a really long pre-rotation log file " * 1000)
    baseline = harness._log_size(str(log))
    # Simulate rotation — truncate to a fresh smaller file with new content.
    log.write_text("[info] pr_merge_update_clusters_affected affected_count=2\n")
    found = harness._scan_log_tail(
        log_path=str(log),
        from_offset=baseline,
        markers=["pr_merge_update_clusters_affected"],
    )
    assert found == {"pr_merge_update_clusters_affected"}


def test_scanner_returns_empty_when_log_missing(tmp_path: Path) -> None:
    """No log file yet -> empty set, no exception."""
    harness = _load_harness()
    found = harness._scan_log_tail(
        log_path=str(tmp_path / "never-existed.log"),
        from_offset=0,
        markers=["anything"],
    )
    assert found == set()


def test_log_size_zero_when_missing(tmp_path: Path) -> None:
    """``_log_size`` returns 0 (not crash) on a missing file."""
    harness = _load_harness()
    assert harness._log_size(str(tmp_path / "never-existed.log")) == 0


def test_poll_short_circuits_when_markers_found(tmp_path: Path) -> None:
    """Polling exits the moment both markers land — no waste of the cap."""
    harness = _load_harness()
    log = tmp_path / "bodhi.log"
    log.write_text(
        "pr_merge_update_clusters_affected affected_count=1\n"
        "job_created job_type=pr_narrow_synthesis\n"
    )
    import time as time_mod

    t0 = time_mod.monotonic()
    found = harness._poll_for_markers(
        log_path=str(log),
        from_offset=0,
        expected={"pr_merge_update_clusters_affected", "pr_narrow_synthesis"},
        deadline_seconds=30,  # would dominate if the early exit didn't fire
    )
    elapsed = time_mod.monotonic() - t0
    assert found == {"pr_merge_update_clusters_affected", "pr_narrow_synthesis"}
    assert elapsed < 1.0  # short-circuit, not the 30s ceiling


def test_poll_returns_partial_match_on_deadline(tmp_path: Path) -> None:
    """If only one marker lands, poll waits then returns the partial set."""
    harness = _load_harness()
    log = tmp_path / "bodhi.log"
    log.write_text("pr_merge_update_clusters_affected only\n")
    found = harness._poll_for_markers(
        log_path=str(log),
        from_offset=0,
        expected={"pr_merge_update_clusters_affected", "pr_narrow_synthesis"},
        deadline_seconds=1,  # short cap so the test is fast
    )
    assert found == {"pr_merge_update_clusters_affected"}
