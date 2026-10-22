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

"""Finishing a Slack status connect: only the signed-in member who started it can."""

import uuid
from types import SimpleNamespace
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest

from app.api.v1 import leave_slack_status
from app.api.v1.leave_slack_status import finish_my_slack_status
from app.api.v1.slack_status_callback import slack_status_callback
from app.schemas.leave_slack_status import SlackStatusFinish
from app.services.leave.slack_status.oauth import (
    Connected,
    UnlinkableSlackAccountError,
    WrongSlackAccountError,
    make_state,
)
from app.services.leave.slack_status.settings import StatusClient
from app.services.slack_user_api import SlackUserApiError

ORG, ME = uuid.uuid4(), uuid.uuid4()
CLIENT = StatusClient(enabled=True, client_id="1.2", client_secret="s")


class FakeDb:
    def __init__(self) -> None:
        self.committed = 0
        self.rolled_back = 0

    async def commit(self) -> None:
        self.committed += 1

    async def rollback(self) -> None:
        self.rolled_back += 1


@pytest.fixture
def exchanged(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Codes that reached ``complete`` (i.e. were exchanged with Slack)."""
    codes: list[str] = []

    async def load_client(*_a: Any) -> StatusClient:
        return CLIENT

    async def complete(_db: Any, _client: Any, _org: Any, _user: Any, code: str) -> Connected:
        codes.append(code)
        return Connected(moved=False, stale_tokens=[])

    async def hand_back(_tokens: list[str]) -> None:
        return None

    monkeypatch.setattr(leave_slack_status, "load_client", load_client)
    monkeypatch.setattr(leave_slack_status, "complete", complete)
    monkeypatch.setattr(leave_slack_status, "hand_back", hand_back)
    monkeypatch.setattr(leave_slack_status, "spawn", lambda coro: coro.close())
    return codes


async def _finish(db: FakeDb, *, started_by: uuid.UUID, signed_in: uuid.UUID) -> str:
    body = SlackStatusFinish(code="code-1", state=make_state(ORG, started_by))
    user = SimpleNamespace(id=signed_in, org_id=ORG)
    result = await finish_my_slack_status(body, user, db)  # type: ignore[arg-type]
    return result.outcome


async def test_the_member_who_started_it_connects(exchanged: list[str]) -> None:
    db = FakeDb()
    assert await _finish(db, started_by=ME, signed_in=ME) == "connected"
    assert exchanged == ["code-1"]
    assert db.committed == 1


async def test_someone_else_signed_in_changes_nothing(exchanged: list[str]) -> None:
    # A colleague opened the member's connect link and approved as themselves.
    db = FakeDb()
    assert await _finish(db, started_by=ME, signed_in=uuid.uuid4()) == "not_yours"
    assert exchanged == []  # the code is never used, so no token is ever issued
    assert db.committed == 0


async def test_a_forged_state_is_expired(exchanged: list[str]) -> None:
    body = SlackStatusFinish(code="code-1", state="not-a-jwt")
    user = SimpleNamespace(id=ME, org_id=ORG)
    result = await finish_my_slack_status(body, user, FakeDb())  # type: ignore[arg-type]
    assert result.outcome == "expired"
    assert exchanged == []


@pytest.mark.parametrize(
    ("error", "outcome"),
    [
        (UnlinkableSlackAccountError(), "unlinkable"),
        (WrongSlackAccountError(), "wrong_account"),
        (SlackUserApiError("token_rotation_on"), "rotation"),
        (SlackUserApiError("invalid_code"), "failed"),
    ],
)
async def test_a_refusal_keeps_nothing(
    monkeypatch: pytest.MonkeyPatch, exchanged: list[str], error: Exception, outcome: str
) -> None:
    async def complete(*_a: Any) -> Connected:
        raise error

    monkeypatch.setattr(leave_slack_status, "complete", complete)
    db = FakeDb()
    assert await _finish(db, started_by=ME, signed_in=ME) == outcome
    assert (db.committed, db.rolled_back) == (0, 1)


async def test_the_callback_only_hands_the_code_to_the_leave_page() -> None:
    response = await slack_status_callback(state="s1", code="c1", error="")
    query = parse_qs(urlparse(response.headers["location"]).query)
    assert query == {"slackCode": ["c1"], "slackState": ["s1"]}
    cancelled = await slack_status_callback(state="s1", code="", error="access_denied")
    assert "slackStatus=cancelled" in cancelled.headers["location"]
