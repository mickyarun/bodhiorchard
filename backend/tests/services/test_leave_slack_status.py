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

"""Which Slack status someone gets, when we may touch it, and the OAuth state."""

import uuid
from datetime import UTC, date, datetime, time

import pytest

from app.core.security import create_access_token, verify_token
from app.models.leave_request import HalfDay, LeaveKind
from app.services.leave.slack_status.oauth import InvalidStateError, make_state, read_state
from app.services.leave.slack_status.plan import (
    LEAVE_EMOJI,
    WFH_EMOJI,
    Booking,
    change_needed,
    is_ours,
    status_for,
)
from app.services.slack_user_api import SlackStatus

TODAY = date(2026, 10, 21)
MIDDAY = time(13)
EARLY = datetime(2026, 10, 20, 12, tzinfo=UTC)  # well before any of today's statuses end
NONE = SlackStatus(text="", emoji="", expiration=0)


def _book(kind: LeaveKind, start: date, end: date, half: HalfDay = HalfDay.NONE) -> Booking:
    return Booking(kind=kind, start=start, end=end, half_day=half)


def _utc(ts: int) -> datetime:
    return datetime.fromtimestamp(ts, UTC)


def test_wfh_today_expires_at_local_midnight() -> None:
    status = status_for([_book(LeaveKind.WFH, TODAY, TODAY)], TODAY, "Asia/Kolkata", MIDDAY, EARLY)
    assert (status.text, status.emoji) == ("Working from home", WFH_EMOJI)
    assert _utc(status.expiration) == datetime(2026, 10, 21, 18, 30, tzinfo=UTC)


def test_a_week_of_leave_is_set_once_until_its_last_day_ends() -> None:
    week = _book(LeaveKind.LEAVE, date(2026, 10, 19), date(2026, 10, 23))
    status = status_for([week], TODAY, "UTC", MIDDAY, EARLY)
    assert (status.text, status.emoji) == ("On leave", LEAVE_EMOJI)
    assert _utc(status.expiration) == datetime(2026, 10, 24, tzinfo=UTC)


def test_morning_off_ends_at_midday_and_never_names_the_type() -> None:
    half = _book(LeaveKind.LEAVE, TODAY, TODAY, HalfDay.FIRST_HALF)
    status = status_for([half], TODAY, "UTC", MIDDAY, EARLY)
    assert status.text == "Off this morning"
    assert _utc(status.expiration) == datetime(2026, 10, 21, 13, tzinfo=UTC)


def test_leave_wins_over_wfh_and_nothing_today_means_no_status() -> None:
    both = [_book(LeaveKind.WFH, TODAY, TODAY), _book(LeaveKind.OPTIONAL_HOLIDAY, TODAY, TODAY)]
    assert status_for(both, TODAY, "UTC", MIDDAY, EARLY).emoji == LEAVE_EMOJI
    tomorrow = _book(LeaveKind.WFH, date(2026, 10, 22), date(2026, 10, 22))
    assert status_for([tomorrow], TODAY, "UTC", MIDDAY, EARLY) == NONE


def test_a_morning_off_approved_after_midday_sets_nothing() -> None:
    half = _book(LeaveKind.LEAVE, TODAY, TODAY, HalfDay.FIRST_HALF)
    afternoon = datetime(2026, 10, 21, 15, tzinfo=UTC)
    assert status_for([half], TODAY, "UTC", MIDDAY, afternoon) == NONE


def test_a_bad_policy_timezone_falls_back_instead_of_failing() -> None:
    status = status_for([_book(LeaveKind.WFH, TODAY, TODAY)], TODAY, "Not/AZone", MIDDAY, EARLY)
    assert status.text == "Working from home"


def test_never_overwrites_or_clears_a_status_the_person_chose() -> None:
    theirs = SlackStatus(text="In Lisbon", emoji=":airplane:", expiration=0)
    ours = SlackStatus(text="Working from home", emoji=WFH_EMOJI, expiration=1)
    assert not is_ours(theirs)
    assert not change_needed(theirs, ours)
    assert not change_needed(theirs, NONE)
    assert change_needed(NONE, ours)
    assert change_needed(ours, NONE)  # cancelled: clear our own status
    assert not change_needed(ours, ours)


def test_state_round_trips_and_is_never_a_login_token() -> None:
    org, user = uuid.uuid4(), uuid.uuid4()
    state = make_state(org, user)
    assert read_state(state) == (org, user)
    assert verify_token(state) is None
    with pytest.raises(InvalidStateError):
        read_state(create_access_token({"sub": str(user)}))
    with pytest.raises(InvalidStateError):
        read_state(state[:-2] + "xx")
