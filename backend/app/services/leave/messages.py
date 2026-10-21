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
"""Notification text for leave requests (pure).

Never includes the leave type or reason: approvers' DMs and in-app
notifications say "requested leave", not "requested sick leave".
"""

from datetime import date
from decimal import Decimal

from app.models.leave_request import LeaveKind, LeaveRequest, LeaveStatus
from app.schemas.leave import HighLeave

_KIND_LABEL = {
    LeaveKind.LEAVE: "leave",
    LeaveKind.WFH: "to work from home",
    LeaveKind.OPTIONAL_HOLIDAY: "an optional holiday",
}


def format_range(start: date, end: date) -> str:
    """ "Mon 20 Oct" or "Mon 20 – Wed 22 Oct" (month repeated only when it changes)."""
    if start == end:
        return f"{start:%a} {start.day} {start:%b}"
    if (start.year, start.month) == (end.year, end.month):
        return f"{start:%a} {start.day} – {end:%a} {end.day} {end:%b}"
    return f"{start:%a} {start.day} {start:%b} – {end:%a} {end.day} {end:%b}"


def number(value: Decimal) -> str:
    """ "4", "10.5": no trailing zeros, no exponent."""
    return f"{value.normalize():f}"


def days_text(days: Decimal) -> str:
    """ "1 day", "2.5 days"."""
    return f"{number(days)} day" if days == 1 else f"{number(days)} days"


def compose_request_message(
    name: str, request: LeaveRequest, *, auto_approved: bool, high_leave: HighLeave | None = None
) -> str:
    """Approver-facing text for a new request (no type, no reason)."""
    when = f"{format_range(request.start_date, request.end_date)} ({days_text(request.days)})"
    what = _KIND_LABEL[request.kind]
    if auto_approved:
        if request.kind == LeaveKind.WFH:
            text = f"{name} is working from home {when}. It was approved automatically."
        else:
            # Only a gender-limited type approves itself today, so "approved
            # automatically" would say which one: plain "on leave" instead.
            text = f"{name} is on leave {when}."
    else:
        text = f"{name} requested {what} {when}."
    return f"{text} {high_leave_line(high_leave)}" if high_leave else text


def high_leave_line(high: HighLeave) -> str:
    """Approvers' line, e.g. With this, they've taken 16 days this year (heads-up at 15)."""
    taken = days_text(high.taken)
    if high.level == "warning":
        return (
            f"With this, they've taken {taken} this year, past the {high.warning_days}-day line."
        )
    return f"With this, they've taken {taken} this year (heads-up at {high.notice_days})."


def already_decided_message(request: LeaveRequest, decider: str | None) -> str:
    """Why a second approver can't decide: who got there first, or that it was cancelled."""
    if request.status == LeaveStatus.CANCELLED:
        return "This request was cancelled."
    verb = {LeaveStatus.APPROVED: "approved", LeaveStatus.REJECTED: "rejected"}.get(request.status)
    if verb is None:
        return "This request changed in the meantime. Refresh and try again."
    return f"{decider} already {verb} this request." if decider else f"Already {verb}."


def compose_decision_message(request: LeaveRequest, decider: str) -> str:
    """Requester-facing text for a decision."""
    verb = "approved" if request.status == LeaveStatus.APPROVED else "rejected"
    what = _KIND_LABEL[request.kind]
    return (
        f"Your request for {what} {format_range(request.start_date, request.end_date)} "
        f"was {verb} by {decider}."
    )
