# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Unit tests for ``make_scan_progress_logger``.

The factory must produce a callable whose signature matches
``ProgressCallback`` (``(tool: str, tool_input: dict) -> None``) and
that emits one structlog ``claude_tool_call`` event per invocation
with the expected fields. We capture via ``structlog.testing.capture_logs``
so the existing global config (stdlib LoggerFactory + file handler) is
respected — the real production logger setup is what should drive these
tests, not a hand-rolled processor stack.
"""

from __future__ import annotations

from structlog.testing import capture_logs

from app.services.scan_phases import make_scan_progress_logger


def test_progress_logger_emits_event_per_tool_call() -> None:
    """Each invocation produces one ``claude_tool_call`` event with phase + scan + tool."""
    cb = make_scan_progress_logger(
        scan_id="abc-123",
        phase="feature_merge",
        repo_name=None,
    )
    with capture_logs() as captured:
        cb("merge_features", {"keep_title": "Feature: Risk"})
        cb("get_pending_features", {})

    events = [e for e in captured if e.get("event") == "claude_tool_call"]
    assert len(events) == 2
    assert events[0]["scan_id"] == "abc-123"
    assert events[0]["phase"] == "feature_merge"
    assert events[0]["tool"] == "merge_features"
    assert events[0]["repo"] is None
    assert events[1]["tool"] == "get_pending_features"


def test_progress_logger_passes_repo_name_for_per_repo_phases() -> None:
    """Per-repo synthesis phase carries the repo name on every event."""
    cb = make_scan_progress_logger(
        scan_id="abc-123",
        phase="feature_synthesis",
        repo_name="ATOACore",
    )
    with capture_logs() as captured:
        cb("write_feature_registry", {"feature_name": "Feature: Auth"})

    events = [e for e in captured if e.get("event") == "claude_tool_call"]
    assert len(events) == 1
    assert events[0]["repo"] == "ATOACore"
    assert events[0]["phase"] == "feature_synthesis"
