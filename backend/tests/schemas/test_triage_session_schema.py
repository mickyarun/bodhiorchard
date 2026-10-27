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

"""TriageSessionRead carries the priority an approved BUD will get."""

import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from app.models.bud import BUDPriority
from app.schemas.triage_session import TriageSessionRead
from app.services import triage_priority


def _read(priority: str | None) -> TriageSessionRead:
    now = datetime.now(UTC)
    return TriageSessionRead(
        id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        slack_channel="C1",
        thread_ts="1.2",
        requester_slack_id="U1",
        status="awaiting_pm",
        priority=priority,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.parametrize(
    "priority,expected",
    [
        ("Critical", BUDPriority.P0),
        ("high", BUDPriority.P1),
        (None, BUDPriority.P2),
        ("nice to have", BUDPriority.P3),
    ],
)
def test_bud_priority_follows_the_normaliser(priority: str | None, expected: BUDPriority) -> None:
    assert _read(priority).bud_priority == expected


def test_bud_priority_is_serialised() -> None:
    assert _read("p1").model_dump(mode="json")["bud_priority"] == "P1"


def test_unknown_priority_preview_does_not_log(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every list call serialises this; only approving the request should log a bad value."""
    fake_logger = MagicMock()
    monkeypatch.setattr(triage_priority, "logger", fake_logger)

    assert _read("super-urgent").model_dump()["bud_priority"] == BUDPriority.P2
    fake_logger.warning.assert_not_called()
