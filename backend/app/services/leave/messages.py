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


def _days(days: Decimal) -> str:
    value = f"{days.normalize():f}"
    return f"{value} day" if days == 1 else f"{value} days"


def compose_request_message(name: str, request: LeaveRequest, *, auto_approved: bool) -> str:
    """Approver-facing text for a new request (no type, no reason)."""
    when = f"{format_range(request.start_date, request.end_date)} ({_days(request.days)})"
    what = _KIND_LABEL[request.kind]
    if auto_approved:
        return f"{name} is working from home {when}. It was approved automatically."
    return f"{name} requested {what} {when}."


def compose_decision_message(request: LeaveRequest, decider: str) -> str:
    """Requester-facing text for a decision."""
    verb = "approved" if request.status == LeaveStatus.APPROVED else "rejected"
    what = _KIND_LABEL[request.kind]
    return (
        f"Your request for {what} {format_range(request.start_date, request.end_date)} "
        f"was {verb} by {decider}."
    )
