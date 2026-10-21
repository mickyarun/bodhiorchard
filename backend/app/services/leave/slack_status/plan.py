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
"""Which Slack status someone should show today, and whether we may touch theirs (pure).

Slack clears it by itself at the expiration, so a status is set once and
never needs a "clear" job. Leave never says its type. We only ever replace
or clear a status we set: anything the person chose themselves wins.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from app.models.leave_request import HalfDay, LeaveKind
from app.services.quiz_schedule_math import resolve_zone
from app.services.slack_user_api import SlackStatus

LEAVE_EMOJI = ":palm_tree:"
WFH_EMOJI = ":house_with_garden:"
_TEXT = {
    (False, HalfDay.NONE): "On leave",
    (False, HalfDay.FIRST_HALF): "Off this morning",
    (False, HalfDay.SECOND_HALF): "Off this afternoon",
    (True, HalfDay.NONE): "Working from home",
    (True, HalfDay.FIRST_HALF): "Working from home this morning",
    (True, HalfDay.SECOND_HALF): "Working from home this afternoon",
}
OURS = {(text, WFH_EMOJI if wfh else LEAVE_EMOJI) for (wfh, _), text in _TEXT.items()}
NO_STATUS = SlackStatus(text="", emoji="", expiration=0)


@dataclass(frozen=True)
class Booking:
    """An approved request, as far as today's status cares."""

    kind: LeaveKind
    start: date
    end: date
    half_day: HalfDay


def status_for(
    bookings: Sequence[Booking], today: date, zone: str, midday: time, now: datetime
) -> SlackStatus:
    """Today's status from approved bookings; :data:`NO_STATUS` = nothing to show.

    Leave wins over WFH. Leave lasts until its last day ends (so a week off
    is set once); WFH and half days end with the day or at midday. One that
    has already ended (a morning off approved in the afternoon) is nothing.
    """
    todays = [b for b in bookings if b.start <= today <= b.end]
    pick = next((b for b in todays if b.kind != LeaveKind.WFH), None) or next(iter(todays), None)
    if pick is None:
        return NO_STATUS
    tz = resolve_zone(zone)
    wfh = pick.kind == LeaveKind.WFH
    last_day = today if wfh else pick.end
    ends = datetime.combine(last_day + timedelta(days=1), time(0), tz)
    if pick.half_day == HalfDay.FIRST_HALF:
        ends = datetime.combine(today, midday, tz)
    if ends <= now:
        return NO_STATUS
    return SlackStatus(
        text=_TEXT[(wfh, pick.half_day)],
        emoji=WFH_EMOJI if wfh else LEAVE_EMOJI,
        expiration=int(ends.timestamp()),
    )


def is_ours(status: SlackStatus) -> bool:
    """A status we set (or none at all), so ours to replace or clear."""
    return (not status.text and not status.emoji) or (status.text, status.emoji) in OURS


def change_needed(current: SlackStatus, wanted: SlackStatus) -> bool:
    """Whether to call Slack: never over the person's own status, never for a no-op."""
    return is_ours(current) and current != wanted
