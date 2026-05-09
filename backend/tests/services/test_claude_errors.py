# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Tests for the Claude subprocess error translator."""

from app.schemas.jobs import JobState, JobStatusRead
from app.services.claude_errors import (
    ClaudeErrorCode,
    from_binary_missing,
    from_returncode,
    from_subtype,
    from_timeout,
)


def test_from_subtype_max_turns_includes_turn_count() -> None:
    code, message = from_subtype("error_max_turns", turns=10)
    assert code is ClaudeErrorCode.MAX_TURNS
    assert "10" in message
    assert "Settings → Agent Prompts" in message
    assert "contact your admin" in message.lower()


def test_from_subtype_max_turns_handles_missing_turn_count() -> None:
    code, message = from_subtype("error_max_turns", turns=None)
    assert code is ClaudeErrorCode.MAX_TURNS
    assert "Settings → Agent Prompts" in message


def test_from_subtype_unknown_preserves_subtype_and_turns_in_detail() -> None:
    code, message = from_subtype("error_during_execution", turns=4)
    assert code is ClaudeErrorCode.UNKNOWN
    assert "error_during_execution" in message
    assert "4 turns" in message


def test_from_subtype_unknown_with_no_turn_count_preserves_subtype_only() -> None:
    code, message = from_subtype("error_during_execution", turns=None)
    assert code is ClaudeErrorCode.UNKNOWN
    assert "error_during_execution" in message
    assert "turns" not in message


def test_from_subtype_with_empty_subtype_yields_generic_unknown() -> None:
    code, message = from_subtype(None)
    assert code is ClaudeErrorCode.UNKNOWN
    assert "AI agent failed unexpectedly" in message


def test_from_timeout_includes_seconds() -> None:
    code, message = from_timeout(900)
    assert code is ClaudeErrorCode.TIMEOUT
    assert "900 seconds" in message


def test_from_timeout_handles_missing_seconds() -> None:
    code, message = from_timeout(None)
    assert code is ClaudeErrorCode.TIMEOUT
    assert "the configured timeout" in message


def test_from_binary_missing_points_to_admin() -> None:
    code, message = from_binary_missing()
    assert code is ClaudeErrorCode.BINARY_MISSING
    assert "Claude CLI is not installed" in message
    assert "admin" in message.lower()


def test_from_returncode_preserves_diagnostic_detail() -> None:
    code, message = from_returncode(1, "stderr line preview")
    assert code is ClaudeErrorCode.UNKNOWN
    assert "exit code 1" in message
    assert "stderr line preview" in message


def test_from_returncode_without_detail_still_friendly() -> None:
    code, message = from_returncode(2, None)
    assert code is ClaudeErrorCode.UNKNOWN
    assert "exit code 2" in message
    assert "AI agent failed" in message


def test_error_codes_are_json_serializable_strings() -> None:
    for code in ClaudeErrorCode:
        assert isinstance(code.value, str)
        assert " " not in code.value


def test_job_status_serializes_error_code_as_camel_case_string() -> None:
    """Wire contract: the frontend keys off ``errorCode`` (camelCase) being
    the StrEnum's plain string value (e.g. ``"max_turns"``). Locking it
    down here so changes to the schema or enum don't silently break the
    frontend translator."""
    status = JobStatusRead(
        job_id="abc",
        job_type="design",
        state=JobState.FAILED,
        error="anything",
        error_code=ClaudeErrorCode.MAX_TURNS,
    )
    payload = status.model_dump(by_alias=True)
    assert payload["errorCode"] == "max_turns"
    assert payload["error"] == "anything"
