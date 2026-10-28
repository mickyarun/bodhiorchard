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

"""Syncing a request to Google Calendar end to end, with Google faked.

The fake calendar holds events by their private tag, as Google does, plus
an event the person made themselves: the sync must never touch it.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

import pytest
from sqlalchemy import select

from app.models.leave_request import LeaveKind, LeaveRequest, LeaveStatus
from app.schemas.leave_calendar_sync import CalendarSyncOptions
from app.services.google.calendar_api import TAG, Event
from app.services.google.service_account import ServiceAccountKey
from app.services.leave.calendar_sync import sync
from app.services.leave.calendar_sync.settings import CalendarSync
from app.services.leave.policies import ensure_default_policy
from tests.integration.leave_edge_support import add_holiday
from tests.integration.leave_support import Factory, add_request, setup_org

pytestmark = pytest.mark.integration
KEY = ServiceAccountKey("bot@proj.iam.gserviceaccount.com", "-----BEGIN PRIVATE KEY-----")
OWN_EVENT = "dentist"


class FakeGoogle:
    """Events by id, each with the tag it carries (None for the person's own)."""

    def __init__(self) -> None:
        self.events: dict[str, str | None] = {OWN_EVENT: None}
        self.tokens_for: list[str] = []

    async def access_token(self, _key: ServiceAccountKey, email: str, _scope: str) -> str:
        self.tokens_for.append(email)
        return "tok"

    async def tagged_event_ids(self, _token: str, tag: str) -> set[str]:
        return {i for i, t in self.events.items() if t == tag}

    async def put_event(self, _token: str, event_id: str, body: Event, *, exists: bool) -> None:
        assert exists == (event_id in self.events)
        self.events[event_id] = body["extendedProperties"]["private"][TAG]

    async def delete_event(self, _token: str, event_id: str) -> None:
        del self.events[event_id]


@pytest.fixture
def google(monkeypatch: pytest.MonkeyPatch, pg_session_factory: Factory) -> FakeGoogle:
    fake = FakeGoogle()
    for name in ("tagged_event_ids", "put_event", "delete_event"):
        monkeypatch.setattr(sync.calendar_api, name, getattr(fake, name))
    monkeypatch.setattr(sync, "access_token", fake.access_token)
    monkeypatch.setattr(sync, "AsyncSessionLocal", pg_session_factory)

    async def active(*_args: Any) -> CalendarSync:
        return CalendarSync(options=CalendarSyncOptions(enabled=True), key=KEY)

    monkeypatch.setattr(sync, "load_sync", active)
    return fake


async def _request_id(factory: Factory, user: uuid.UUID) -> uuid.UUID:
    """The id of ``user``'s only request."""
    async with factory() as db:
        return (
            await db.scalars(select(LeaveRequest.id).where(LeaveRequest.user_id == user))
        ).one()


async def _set_status(factory: Factory, request_id: uuid.UUID, status: LeaveStatus) -> None:
    async with factory() as db:
        request = await db.get(LeaveRequest, request_id)
        assert request is not None
        request.status = status
        await db.commit()


async def test_approved_wfh_gets_one_entry_per_working_day_then_cancel_removes_only_ours(
    pg_session_factory: Factory, google: FakeGoogle
) -> None:
    org, (emp, peer), _ = await setup_org(pg_session_factory, "Emp", "Peer")
    # Mon to Sun with a Wednesday holiday: four working days at home.
    await add_request(
        pg_session_factory, org, emp, date(2030, 6, 10), date(2030, 6, 16), "4", kind=LeaveKind.WFH
    )
    await add_request(
        pg_session_factory,
        org,
        peer,
        date(2030, 6, 10),
        date(2030, 6, 10),
        "1",
        kind=LeaveKind.WFH,
    )
    mine = await _request_id(pg_session_factory, emp)
    theirs = await _request_id(pg_session_factory, peer)
    async with pg_session_factory() as db:
        policy = await ensure_default_policy(db, org)
    await add_holiday(pg_session_factory, org, policy.id, date(2030, 6, 12), "Fest")
    await sync.sync_request(org, mine)
    await sync.sync_request(org, theirs)
    ours = {i for i, tag in google.events.items() if tag == mine.hex}
    days = ("20300610", "20300611", "20300613", "20300614")
    assert ours == {f"bo{mine.hex}d{day}" for day in days}
    # Running it again changes nothing.
    await sync.sync_request(org, mine)
    assert {i for i, tag in google.events.items() if tag == mine.hex} == ours

    await _set_status(pg_session_factory, mine, LeaveStatus.CANCELLED)
    await sync.sync_request(org, mine)
    assert not any(tag == mine.hex for tag in google.events.values())
    # The person's own event and a colleague's entry are untouched.
    assert google.events[OWN_EVENT] is None
    assert list(google.events.values()).count(theirs.hex) == 1


async def test_pending_or_another_orgs_request_writes_nothing(
    pg_session_factory: Factory, google: FakeGoogle
) -> None:
    org, (emp,), casual = await setup_org(pg_session_factory, "Emp")
    other, _, _ = await setup_org(pg_session_factory, "Other")
    await add_request(
        pg_session_factory, org, emp, date(2030, 6, 10), date(2030, 6, 10), "1",
        type_id=casual, status=LeaveStatus.PENDING,
    )  # fmt: skip
    pending = await _request_id(pg_session_factory, emp)
    await sync.sync_request(org, pending)
    assert google.events == {OWN_EVENT: None}
    # Approved, but asked for under another org: not found there, no calendar opened.
    opened = len(google.tokens_for)
    await _set_status(pg_session_factory, pending, LeaveStatus.APPROVED)
    await sync.sync_request(other, pending)
    assert google.events == {OWN_EVENT: None} and len(google.tokens_for) == opened
