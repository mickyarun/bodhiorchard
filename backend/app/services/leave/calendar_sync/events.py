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
"""The Google Calendar events an approved request should have (pure).

Leave (and an optional holiday) is one "Out of office" event over the
whole range: Google requires it to be timed, so it runs midnight to
midnight in the requester's timezone, or to/from midday for a half day.
WFH is a "Home" working location on each working day: an all-day one
can't span days, and weekends and holidays aren't WFH.

Titles never say the leave type or reason; anyone who can see the
calendar sees only "Out of office".
"""

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.models.leave_request import HalfDay, LeaveKind
from app.schemas.leave_calendar_sync import CalendarSyncOptions
from app.services.google.calendar_api import TAG, Event
from app.services.leave.calendar_math import iter_dates

OOO_TITLE = "Out of office"
HOME_TITLE = "Home"
DESCRIPTION = "Added by Glideship from an approved request."


@dataclass(frozen=True)
class RequestShape:
    """The parts of a request and its policy that decide the events."""

    request_hex: str  # the request id's 32 hex digits
    kind: LeaveKind
    start: date
    end: date
    half_day: HalfDay
    timezone: str
    working_days: Collection[int]
    holidays: Mapping[date, str]


def event_id(shape: RequestShape, day: date | None = None) -> str:
    """Our id for an event: Google allows 0-9 and a-v, and hex digits fit."""
    return f"bo{shape.request_hex}" + (f"d{day:%Y%m%d}" if day else "")


def _span(shape: RequestShape, midday: time) -> tuple[datetime, datetime]:
    zone = ZoneInfo(shape.timezone)
    start = datetime.combine(shape.start, time(0), zone)
    end = datetime.combine(shape.end + timedelta(days=1), time(0), zone)
    if shape.half_day == HalfDay.FIRST_HALF:
        end = datetime.combine(shape.start, midday, zone)
    elif shape.half_day == HalfDay.SECOND_HALF:
        start = datetime.combine(shape.start, midday, zone)
    return start, end


def _timed(start: datetime, end: datetime, zone: str) -> dict[str, Any]:
    return {
        "start": {"dateTime": start.isoformat(), "timeZone": zone},
        "end": {"dateTime": end.isoformat(), "timeZone": zone},
    }


def _base(shape: RequestShape) -> Event:
    return {
        "description": DESCRIPTION,
        "extendedProperties": {"private": {TAG: shape.request_hex}},
    }


def _out_of_office(shape: RequestShape, options: CalendarSyncOptions, midday: time) -> Event:
    start, end = _span(shape, midday)
    return {
        **_base(shape),
        **_timed(start, end, shape.timezone),
        "summary": OOO_TITLE,
        "eventType": "outOfOffice",
        "transparency": "opaque",
        "outOfOfficeProperties": {
            "autoDeclineMode": "declineOnlyNewConflictingInvitations"
            if options.decline_meetings
            else "declineNone",
            "declineMessage": options.decline_message,
        },
    }


def _home(shape: RequestShape, day: date, midday: time) -> Event:
    when: dict[str, Any]
    if shape.half_day == HalfDay.NONE:
        when = {
            "start": {"date": day.isoformat()},
            "end": {"date": (day + timedelta(1)).isoformat()},
        }
    else:
        when = _timed(*_span(shape, midday), shape.timezone)
    return {
        **_base(shape),
        **when,
        "summary": HOME_TITLE,
        "eventType": "workingLocation",
        "visibility": "public",
        "transparency": "transparent",
        "workingLocationProperties": {"type": "homeOffice", "homeOffice": {}},
    }


def desired_events(shape: RequestShape, options: CalendarSyncOptions) -> dict[str, Event]:
    """Event id → body for an approved request."""
    midday = time.fromisoformat(options.midday)
    if shape.kind != LeaveKind.WFH:
        return {event_id(shape): _out_of_office(shape, options, midday)}
    return {
        event_id(shape, day): _home(shape, day, midday)
        for day in iter_dates(shape.start, shape.end)
        if day.weekday() in shape.working_days and day not in shape.holidays
    }


def wanted_events(
    shape: RequestShape, options: CalendarSyncOptions, *, approved: bool
) -> dict[str, Event]:
    """What should be on the calendar: the events when on and approved, else nothing."""
    return desired_events(shape, options) if options.enabled and approved else {}


# Status events (Out of office, working location) aren't on every Google
# Workspace edition: Business Starter has no working location, for one.
STATUS_TYPES = {"outOfOffice", "workingLocation"}
_PLAIN_TITLE = {"outOfOffice": OOO_TITLE, "workingLocation": "Working from home"}
_STATUS_FIELDS = ("eventType", "outOfOfficeProperties", "workingLocationProperties")


def plain_event(body: Event) -> Event:
    """The same entry as an ordinary event, for editions without status events.

    Same dates, tag and busy/free; an Out of office stays busy, working from
    home stays free. It just can't decline meetings or set a work location.
    """
    plain = {k: v for k, v in body.items() if k not in _STATUS_FIELDS}
    plain["summary"] = _PLAIN_TITLE.get(str(body.get("eventType")), str(body.get("summary", "")))
    plain["visibility"] = "default"
    return plain
