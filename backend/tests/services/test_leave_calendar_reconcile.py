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

"""Reconciling a calendar against a request, and reading service account keys."""

import json
from typing import Any

import pytest

from app.schemas.leave_calendar_sync import CalendarSyncOptions
from app.services.google import service_account
from app.services.google.calendar_api import Event
from app.services.google.service_account import GoogleAuthError, ServiceAccountKey, parse_key
from app.services.leave.calendar_sync import sync
from app.services.leave.calendar_sync.settings import CalendarSync

KEY = ServiceAccountKey("bot@proj.iam.gserviceaccount.com", "-----BEGIN PRIVATE KEY-----")


class FakeCalendar:
    """Records writes; ``existing`` is what's already tagged on the calendar."""

    def __init__(self, existing: set[str]) -> None:
        self.existing = existing
        self.puts: list[tuple[str, bool]] = []
        self.deletes: list[str] = []

    async def tagged_event_ids(self, _token: str, _tag: str) -> set[str]:
        return set(self.existing)

    async def put_event(self, _token: str, event_id: str, _body: Event, *, exists: bool) -> None:
        self.puts.append((event_id, exists))

    async def delete_event(self, _token: str, event_id: str) -> None:
        self.deletes.append(event_id)


@pytest.fixture
def calendar(monkeypatch: pytest.MonkeyPatch) -> FakeCalendar:
    fake = FakeCalendar(existing={"keep", "stale"})
    for name in ("tagged_event_ids", "put_event", "delete_event"):
        monkeypatch.setattr(sync.calendar_api, name, getattr(fake, name))

    async def token(*_args: Any) -> str:
        return "tok"

    monkeypatch.setattr(sync, "access_token", token)
    return fake


async def test_updates_wanted_creates_missing_and_removes_the_rest(calendar: FakeCalendar) -> None:
    active = CalendarSync(options=CalendarSyncOptions(enabled=True), key=KEY)
    await sync._apply(active, "ravi@co.com", "tag", {"keep": {}, "new": {}})
    assert sorted(calendar.puts) == [("keep", True), ("new", False)]
    assert calendar.deletes == ["stale"]


async def test_nothing_wanted_clears_the_request(calendar: FakeCalendar) -> None:
    active = CalendarSync(options=CalendarSyncOptions(enabled=True), key=KEY)
    await sync._apply(active, "ravi@co.com", "tag", {})
    assert calendar.puts == []
    assert sorted(calendar.deletes) == ["keep", "stale"]


def test_cache_is_keyed_on_the_private_key_not_the_public_email() -> None:
    forged = ServiceAccountKey(KEY.client_email, "another key")
    assert forged.fingerprint != KEY.fingerprint


def test_parse_key_reads_a_service_account_json_and_ignores_its_token_uri() -> None:
    raw = json.dumps(
        {
            "type": "service_account",
            "client_email": KEY.client_email,
            "private_key": "pem",
            "token_uri": "http://169.254.169.254/latest",
        }
    )
    key = parse_key(raw)
    assert key.client_email == KEY.client_email
    assert not hasattr(key, "token_uri")
    assert service_account.TOKEN_URI.startswith("https://oauth2.googleapis.com/")


@pytest.mark.parametrize(
    "raw",
    ["not json", json.dumps({"type": "authorized_user"}), json.dumps({"type": "service_account"})],
)
def test_parse_key_refuses_anything_else(raw: str) -> None:
    with pytest.raises(GoogleAuthError):
        parse_key(raw)
