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

"""Free-text triage priority → structured BUDPriority normalizer."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.models.bud import BUDPriority
from app.services import slack_intake
from app.services.slack_intake import normalize_triage_priority


@pytest.mark.parametrize(
    "raw,expected",
    [
        # P0 synonyms
        ("critical", BUDPriority.P0),
        ("urgent", BUDPriority.P0),
        ("blocker", BUDPriority.P0),
        ("asap", BUDPriority.P0),
        ("highest", BUDPriority.P0),
        ("P0", BUDPriority.P0),
        ("p0", BUDPriority.P0),
        ("sev0", BUDPriority.P0),
        # P1
        ("high", BUDPriority.P1),
        ("P1", BUDPriority.P1),
        ("sev1", BUDPriority.P1),
        # P2 default-ish synonyms
        ("medium", BUDPriority.P2),
        ("normal", BUDPriority.P2),
        ("P2", BUDPriority.P2),
        ("sev2", BUDPriority.P2),
        # P3
        ("low", BUDPriority.P3),
        ("minor", BUDPriority.P3),
        ("lowest", BUDPriority.P3),
        ("P3", BUDPriority.P3),
        ("sev3", BUDPriority.P3),
        ("nice to have", BUDPriority.P3),
        ("nice-to-have", BUDPriority.P3),
        # Punctuation / hyphen / typed-emphasis — separator-stripped lookup
        ("P-0", BUDPriority.P0),
        ("p0!", BUDPriority.P0),
        ("sev-1", BUDPriority.P1),
        ("p_2", BUDPriority.P2),
        # Whitespace + casing
        ("  Critical  ", BUDPriority.P0),
        ("HIGH", BUDPriority.P1),
        # Unknown / empty → default P2 (matches column server_default)
        ("super-urgent", BUDPriority.P2),
        ("", BUDPriority.P2),
        (None, BUDPriority.P2),
    ],
)
def test_normalize_triage_priority(raw: str | None, expected: BUDPriority) -> None:
    assert normalize_triage_priority(raw) == expected


def test_unknown_priority_logs_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unknown-but-truthy values must emit a triage_priority_unknown warning.

    Empty / None stay silent (documented default), but typos and
    unmapped variants should leave an operator-visible breadcrumb.
    structlog routes through its own logger instance so caplog (stdlib)
    can't see it — patch the module logger directly per repo convention.
    """
    fake_logger = MagicMock()
    monkeypatch.setattr(slack_intake, "logger", fake_logger)

    assert normalize_triage_priority("super-urgent") == BUDPriority.P2
    fake_logger.warning.assert_called_once_with("triage_priority_unknown", raw="super-urgent")


def test_empty_priority_does_not_log(monkeypatch: pytest.MonkeyPatch) -> None:
    """None / empty string should not emit a warning — that's the documented default."""
    fake_logger = MagicMock()
    monkeypatch.setattr(slack_intake, "logger", fake_logger)

    normalize_triage_priority(None)
    normalize_triage_priority("")
    fake_logger.warning.assert_not_called()
