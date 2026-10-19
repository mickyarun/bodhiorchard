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

"""The text of the daily who's-out post (pure, no I/O).

Plain names, not @mentions, so people who are out aren't pinged on their
day off. Names are escaped so one can't smuggle in <!channel> or a link.
Never the leave type or reason: just who is out or working from home,
and when they're back.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta

from app.models.leave_request import HalfDay
from app.services.leave.slack_blocks import escape


@dataclass(frozen=True)
class OutToday:
    """One person away or remote today."""

    name: str
    half_day: HalfDay
    # Their next working day after this request; None if not known.
    back_on: date | None


def _when(person: OutToday, today: date) -> str:
    if person.half_day == HalfDay.FIRST_HALF:
        return "out this morning"
    if person.half_day == HalfDay.SECOND_HALF:
        return "out this afternoon"
    if person.back_on is None:
        return ""
    if person.back_on == today + timedelta(days=1):
        return "back tomorrow"
    if person.back_on - today < timedelta(days=7):
        return f"back {person.back_on:%a}"
    return f"back {person.back_on.day} {person.back_on:%b}"


def _wfh(person: OutToday) -> str:
    if person.half_day == HalfDay.FIRST_HALF:
        return "morning"
    if person.half_day == HalfDay.SECOND_HALF:
        return "afternoon"
    return ""


def _names(people: list[OutToday], detail: Callable[[OutToday], str]) -> str:
    parts = []
    for person in sorted(people, key=lambda p: p.name.lower()):
        extra = detail(person)
        name = escape(person.name)
        parts.append(f"{name} ({extra})" if extra else name)
    return ", ".join(parts)


def compose(
    today: date, away: list[OutToday], remote: list[OutToday], holidays: list[str]
) -> str | None:
    """The post for ``today``, or None when there's nothing to say."""
    if not away and not remote and not holidays:
        return None
    lines = [f"*Who's out today, {today:%a} {today.day} {today:%b}*"]
    if away:
        lines.append(f"On leave: {_names(away, lambda p: _when(p, today))}")
    if remote:
        lines.append(f"Working from home: {_names(remote, _wfh)}")
    for holiday in holidays:
        lines.append(f"Holiday: {escape(holiday)}")
    return "\n".join(lines)
