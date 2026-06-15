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

"""Pure time math for the quiz scheduler — weekday gate + fire-window instants.

Kept free of I/O and ``datetime.now`` so the (DST-sensitive) logic is fully
unit-testable: the caller passes ``now_utc`` and a resolved ``tzinfo``. Firing
uses ``>=`` (not ``==``) so a missed tick or a DST spring-forward never skips the
day, and the open/reveal instants are absolute UTC, locked at open time.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta, tzinfo
from zoneinfo import ZoneInfo

import structlog

logger = structlog.get_logger(__name__)


def resolve_zone(name: str | None) -> tzinfo:
    """Resolve an IANA name to a zone; fall back to the server-local zone."""
    if name:
        try:
            return ZoneInfo(name)
        except Exception:
            logger.warning("quiz_bad_timezone", name=name)
    return datetime.now(UTC).astimezone().tzinfo or UTC


@dataclass(slots=True, frozen=True)
class OpenWindow:
    """The resolved instants for opening a quiz on a given local date."""

    quiz_date: date
    open_at: datetime  # absolute UTC
    reveal_at: datetime  # absolute UTC


def parse_hhmm(value: str) -> time:
    """Parse a validated ``HH:MM`` string into a ``time``."""
    hour, minute = value.split(":")
    return time(int(hour), int(minute))


def previous_month_key(today: date) -> str:
    """Return the ``YYYY-MM`` key for the month before ``today``'s month."""
    last_of_prev = today.replace(day=1) - timedelta(days=1)
    return last_of_prev.strftime("%Y-%m")


def current_month_key(today: date) -> str:
    """Return the ``YYYY-MM`` key for ``today``'s month."""
    return today.strftime("%Y-%m")


def month_bounds(period_month: str) -> tuple[date, date]:
    """Return ``(first_day, first_day_of_next_month)`` for a ``YYYY-MM`` key."""
    year, month = (int(p) for p in period_month.split("-"))
    start = date(year, month, 1)
    end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return start, end


def next_quiz_at(
    *,
    now_utc: datetime,
    zone: tzinfo,
    quiz_time: str,
    active_weekdays: list[int],
) -> datetime | None:
    """Return the next UTC instant a quiz will open, or None if none scheduled.

    Scans the next two weeks of local days for the first active weekday whose
    local ``quiz_time`` is still in the future.
    """
    if not active_weekdays:
        return None
    now_local = now_utc.astimezone(zone)
    target = parse_hhmm(quiz_time)
    for offset in range(0, 14):
        day = now_local.date() + timedelta(days=offset)
        if day.weekday() not in active_weekdays:
            continue
        candidate = datetime.combine(day, target, tzinfo=zone).astimezone(UTC)
        if candidate > now_utc:
            return candidate
    return None


def compute_open_window(
    *,
    now_utc: datetime,
    zone: tzinfo,
    quiz_time: str,
    active_weekdays: list[int],
    window_minutes: int,
) -> OpenWindow | None:
    """Return the open window if a quiz should fire now in ``zone``, else None.

    A quiz fires when, in the org's local time, today is an active weekday and
    the local clock has reached ``quiz_time``. The returned instants are UTC.
    Idempotency (one quiz per org-day) is the caller's/DB's job — this only says
    "it is at or past today's fire time on a quiz day".
    """
    now_local = now_utc.astimezone(zone)
    if now_local.weekday() not in active_weekdays:
        return None

    target = parse_hhmm(quiz_time)
    if now_local.timetz().replace(tzinfo=None) < target:
        return None

    quiz_date = now_local.date()
    open_local = datetime.combine(quiz_date, target, tzinfo=zone)
    open_at = open_local.astimezone(UTC)
    reveal_at = open_at + timedelta(minutes=window_minutes)
    return OpenWindow(quiz_date=quiz_date, open_at=open_at, reveal_at=reveal_at)
