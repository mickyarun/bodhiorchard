# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Unit tests for the Claude CLI error-extraction helpers.

Parked under ``tests/services/platforms/`` to reuse the lightweight
conftest that overrides the DB autouse fixture — these are pure-function
tests.
"""

from __future__ import annotations

from app.services.claude_runner import _extract_event_error, _parse_cli_error_payload


def test_event_error_pattern_is_error_true() -> None:
    event = {"is_error": True, "result": "Credit balance is too low", "api_error_status": 400}
    out = _extract_event_error(event)
    assert out == "Credit balance is too low (HTTP 400)"


def test_event_error_pattern_is_error_true_no_status() -> None:
    event = {"is_error": True, "result": "Authentication required"}
    assert _extract_event_error(event) == "Authentication required"


def test_event_error_pattern_type_error_with_message() -> None:
    event = {"type": "error", "message": "Session ended unexpectedly"}
    assert _extract_event_error(event) == "Session ended unexpectedly"


def test_event_error_pattern_type_error_nested_dict() -> None:
    event = {"type": "error", "error": {"type": "rate_limit", "message": "Too many requests"}}
    assert _extract_event_error(event) == "Too many requests"


def test_event_error_pattern_type_error_nested_string() -> None:
    event = {"type": "error", "error": "Model deprecated"}
    assert _extract_event_error(event) == "Model deprecated"


def test_event_error_pattern_result_with_error_subtype() -> None:
    event = {"type": "result", "subtype": "error_max_turns", "result": "Hit 15-turn cap"}
    assert _extract_event_error(event) == "error_max_turns: Hit 15-turn cap"


def test_event_error_returns_none_for_success_event() -> None:
    event = {"type": "result", "subtype": "success", "result": "hello", "is_error": False}
    assert _extract_event_error(event) is None


def test_event_error_returns_none_for_non_error_types() -> None:
    assert _extract_event_error({"type": "assistant", "message": {}}) is None
    assert _extract_event_error({"type": "system", "subtype": "init"}) is None


def test_event_error_truncates_to_500_chars() -> None:
    event = {"is_error": True, "result": "x" * 2000}
    out = _extract_event_error(event)
    assert out is not None
    assert len(out) <= 500


def test_parse_cli_error_payload_still_works() -> None:
    # Regression: ensure the existing helper used by the non-streaming
    # path is untouched.
    stdout = '{"is_error": true, "result": "boom", "api_error_status": 500}'
    assert _parse_cli_error_payload(stdout) == "boom (HTTP 500)"
