# Copyright 2025-2026 Arun Rajkumar
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
"""Tests for the code-review output parse-failure classifier.

These pin the ``parse_failure_reason`` precedence so the Code Review tab
banner stays accurate as new failure modes get added.
"""

import pytest

from app.schemas.bud_code_review import PARSE_FAILURE_MESSAGES
from app.services.agent_result_handlers import _parse_code_review_output, is_git_auth_failure


@pytest.mark.parametrize(
    "fragment",
    [
        "remote: Invalid username or token. Password authentication is not supported",
        "fatal: Authentication failed for 'https://github.com/foo/bar.git/'",
        "could not read Username for 'https://github.com'",
        "remote: Repository not found.",
        "fatal: unable to access 'https://github.com/foo/bar/': The requested URL returned 403",
        "Bad credentials",
    ],
)
def test_git_auth_failure_classified(fragment: str) -> None:
    result = _parse_code_review_output(f"Plain prose, no JSON here.\n{fragment}\n")
    assert result["_parse_ok"] is False
    assert result["_parse_failure_reason"] == "git_auth_failed"
    assert result["code_review_comments"] == []


def test_git_auth_failure_beats_insight_contamination() -> None:
    output = (
        "★ Insight ─────────────────────────────────────\n"
        "some learning content\n"
        "─────────────────────────────────────────────────\n"
        "remote: Invalid username or token.\n"
    )
    result = _parse_code_review_output(output)
    assert result["_parse_failure_reason"] == "git_auth_failed"


def test_no_json_when_no_known_signal() -> None:
    result = _parse_code_review_output("just some prose with no json and no auth error")
    assert result["_parse_failure_reason"] == "no_json"


def test_is_git_auth_failure_matches_same_signals_as_parser() -> None:
    # Shared with bud_agent_handler's retry path — keep the detector
    # and classifier in lockstep by going through this helper.
    assert is_git_auth_failure("remote: Invalid username or token.") is True
    assert is_git_auth_failure("Bad credentials") is True
    assert is_git_auth_failure("nothing wrong here") is False
    assert is_git_auth_failure("") is False


def test_banner_copy_exists_for_classifier_reasons() -> None:
    reasons = (
        "git_auth_failed",
        "insight_contaminated",
        "no_json",
        "not_dict",
        "parse_exception",
    )
    for reason in reasons:
        assert reason in PARSE_FAILURE_MESSAGES, f"missing banner copy for {reason}"
