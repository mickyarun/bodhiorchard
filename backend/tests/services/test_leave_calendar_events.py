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

"""The Google Calendar events an approved request turns into."""

import re
import uuid
from datetime import date

from app.models.leave_request import HalfDay, LeaveKind
from app.schemas.leave_calendar_sync import CalendarSyncOptions
from app.services.google.calendar_api import TAG
from app.services.leave.calendar_sync.events import (
    RequestShape,
    desired_events,
    plain_event,
    wanted_events,
)

MON_FRI = [0, 1, 2, 3, 4]
REQUEST = uuid.UUID("0123456789abcdef0123456789abcdef")
GOOGLE_ID = re.compile(r"^[a-v0-9]{5,1024}$")


def _shape(**overrides: object) -> RequestShape:
    base: dict[str, object] = {
        "request_hex": REQUEST.hex,
        "kind": LeaveKind.LEAVE,
        "start": date(2026, 10, 23),  # Fri
        "end": date(2026, 10, 27),  # Tue
        "half_day": HalfDay.NONE,
        "timezone": "Asia/Kolkata",
        "working_days": MON_FRI,
        "holidays": {},
    }
    return RequestShape(**{**base, **overrides})  # type: ignore[arg-type]


def test_leave_is_one_timed_out_of_office_over_the_whole_range() -> None:
    events = desired_events(_shape(), CalendarSyncOptions())
    assert len(events) == 1
    ((event_id, body),) = events.items()
    assert GOOGLE_ID.match(event_id)
    assert body["eventType"] == "outOfOffice"
    assert body["start"]["dateTime"] == "2026-10-23T00:00:00+05:30"
    assert body["end"]["dateTime"] == "2026-10-28T00:00:00+05:30"
    assert body["outOfOfficeProperties"]["autoDeclineMode"] == (
        "declineOnlyNewConflictingInvitations"
    )
    assert body["extendedProperties"]["private"][TAG] == REQUEST.hex


def test_title_never_names_the_type() -> None:
    (body,) = desired_events(_shape(), CalendarSyncOptions()).values()
    assert body["summary"] == "Out of office"


def test_half_days_split_at_the_configured_midday() -> None:
    options = CalendarSyncOptions(midday="12:30", decline_meetings=False)
    one_day = {"start": date(2026, 10, 23), "end": date(2026, 10, 23)}
    (morning,) = desired_events(_shape(**one_day, half_day=HalfDay.FIRST_HALF), options).values()
    assert morning["start"]["dateTime"] == "2026-10-23T00:00:00+05:30"
    assert morning["end"]["dateTime"] == "2026-10-23T12:30:00+05:30"
    assert morning["outOfOfficeProperties"]["autoDeclineMode"] == "declineNone"
    (afternoon,) = desired_events(
        _shape(**one_day, half_day=HalfDay.SECOND_HALF), options
    ).values()
    assert afternoon["start"]["dateTime"] == "2026-10-23T12:30:00+05:30"
    assert afternoon["end"]["dateTime"] == "2026-10-24T00:00:00+05:30"


def test_wfh_is_one_all_day_home_entry_per_working_day() -> None:
    shape = _shape(kind=LeaveKind.WFH, holidays={date(2026, 10, 26): "Diwali"})
    events = desired_events(shape, CalendarSyncOptions())
    # Fri 23 and Tue 27: the weekend and the Monday holiday are skipped.
    days = sorted(body["start"]["date"] for body in events.values())
    assert days == ["2026-10-23", "2026-10-27"]
    for event_id, body in events.items():
        assert GOOGLE_ID.match(event_id)
        assert body["eventType"] == "workingLocation"
        assert body["workingLocationProperties"]["type"] == "homeOffice"
    assert len(set(events)) == 2


def test_half_day_wfh_is_timed() -> None:
    shape = _shape(
        kind=LeaveKind.WFH,
        start=date(2026, 10, 23),
        end=date(2026, 10, 23),
        half_day=HalfDay.SECOND_HALF,
    )
    (body,) = desired_events(shape, CalendarSyncOptions()).values()
    assert body["start"]["dateTime"] == "2026-10-23T13:00:00+05:30"


def test_switched_off_or_not_approved_wants_nothing_so_events_are_removed() -> None:
    on, off = CalendarSyncOptions(enabled=True), CalendarSyncOptions(enabled=False)
    assert wanted_events(_shape(), on, approved=True)
    assert wanted_events(_shape(), on, approved=False) == {}
    assert wanted_events(_shape(), off, approved=True) == {}


def test_plain_versions_keep_dates_tag_and_busy_free_without_status_fields() -> None:
    (ooo,) = desired_events(_shape(), CalendarSyncOptions()).values()
    plain = plain_event(ooo)
    assert "eventType" not in plain and "outOfOfficeProperties" not in plain
    assert plain["summary"] == "Out of office" and plain["transparency"] == "opaque"
    assert (
        plain["start"] == ooo["start"] and plain["extendedProperties"] == ooo["extendedProperties"]
    )

    home = next(iter(desired_events(_shape(kind=LeaveKind.WFH), CalendarSyncOptions()).values()))
    plain_home = plain_event(home)
    assert plain_home["summary"] == "Working from home"
    assert plain_home["transparency"] == "transparent"
    assert "workingLocationProperties" not in plain_home
