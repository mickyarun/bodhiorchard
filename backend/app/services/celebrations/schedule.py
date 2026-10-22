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

"""When a celebration digest fires, and which dates it covers.

Mirrors ``quiz_schedule_math``: the scheduler re-derives the local fire
time on every 60s tick rather than sleeping until a precomputed instant,
so the result is naturally DST-correct and self-heals after a restart.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, tzinfo

from app.schemas.settings import CelebrationWeekendPolicy
from app.services.quiz_schedule_math import parse_hhmm, resolve_zone

__all__ = [
    "MAX_SPAN_DAYS",
    "POST_WINDOW",
    "PostWindow",
    "compute_post_window",
    "covered_dates",
    "resolve_zone",
]

# A digest never reaches back or forward further than this many days, so a
# misconfigured weekday set (e.g. "Mondays only") cannot make one post
# announce a fortnight of birthdays at once.
MAX_SPAN_DAYS = 6

# How long after ``post_time`` a digest may still go out. Without a cap the
# window runs to local midnight, so a restart at 23:40, switching the feature
# on at 22:00, or HR entering a birth date mid-afternoon would post (perhaps
# with ``@channel``) in the middle of the evening. Late enough to ride out a
# deploy or a short Slack outage; a day missed beyond it stays missed.
POST_WINDOW = timedelta(hours=3)


@dataclass(slots=True, frozen=True)
class PostWindow:
    """The resolved instant and coverage for one digest."""

    # The org-local date the digest is posted on; the ledger's idempotency key.
    post_date: date
    # Every calendar date this digest announces, ascending, including post_date
    # when it is itself covered.
    occasions: tuple[date, ...]
    # Absolute UTC instant the window opened.
    post_at: datetime


def covered_dates(
    post_date: date,
    *,
    active_weekdays: list[int],
    policy: CelebrationWeekendPolicy,
) -> tuple[date, ...]:
    """Which calendar dates a digest posted on ``post_date`` announces.

    ``post_date`` is always an active weekday (the caller checked). The
    question is what happens to celebrations that land on the *inactive*
    days around it — a Saturday birthday when the org only posts Mon–Fri.

    Args:
        post_date: The active weekday the digest goes out on.
        active_weekdays: Posting days, Python ``date.weekday()`` ints (Mon=0).
        policy: How to treat celebrations on inactive days.

    Returns:
        Ascending dates to announce, always including ``post_date``.
    """
    active = set(active_weekdays)
    # The default schedule posts every day, so nothing is ever skipped and
    # there is no gap to roll across. Checked before ``policy`` so the knob
    # is simply inert rather than subtly wrong on a 7-day schedule.
    if len(active) >= 7 or policy is CelebrationWeekendPolicy.SKIP:
        return (post_date,)
    if post_date.weekday() not in active:
        # Defensive: the scheduler only calls this on an active weekday, but
        # the manual test-post endpoint can fire on any day.
        return (post_date,)

    # ROLL_FORWARD looks *backwards* from the post date and absorbs the
    # inactive run behind it; ROLL_BACKWARD looks ahead. Walking from the
    # post date outwards (rather than from each gap forwards) is what makes
    # coverage exactly-once: each inactive run is claimed by precisely one
    # neighbouring post.
    direction = -1 if policy is CelebrationWeekendPolicy.ROLL_FORWARD else 1
    covered = [post_date]
    for offset in range(1, MAX_SPAN_DAYS + 1):
        day = _step(post_date, direction * offset)
        if day.weekday() in active:
            # Reached the neighbouring post; that day owns everything beyond.
            break
        covered.append(day)
    return tuple(sorted(covered))


def compute_post_window(
    *,
    now_utc: datetime,
    zone: tzinfo,
    post_time: str,
    active_weekdays: list[int],
    policy: CelebrationWeekendPolicy,
) -> PostWindow | None:
    """Return the window if a digest should fire now in ``zone``, else None.

    Fires when, in org-local time, today is an active weekday and the local
    clock is between ``post_time`` and ``post_time + POST_WINDOW``. Says
    nothing about whether today's digest was already sent — that is the
    ledger's job.
    """
    now_local = now_utc.astimezone(zone)
    if now_local.weekday() not in active_weekdays:
        return None

    target = parse_hhmm(post_time)
    if now_local.timetz().replace(tzinfo=None) < target:
        return None

    post_date = now_local.date()
    post_at = datetime.combine(post_date, target, tzinfo=zone).astimezone(UTC)
    # Compared in UTC so a DST change inside the window cannot stretch or
    # shrink it.
    if now_utc.astimezone(UTC) > post_at + POST_WINDOW:
        return None
    return PostWindow(
        post_date=post_date,
        occasions=covered_dates(post_date, active_weekdays=active_weekdays, policy=policy),
        post_at=post_at,
    )


def _step(day: date, delta: int) -> date:
    """``day`` shifted by ``delta`` days."""
    return day + timedelta(days=delta)
