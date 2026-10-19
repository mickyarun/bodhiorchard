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

"""Who's out today, gathered for the daily post.

Each person is judged on their own policy's calendar: someone on a policy
whose day off it is doesn't appear, and a public holiday on one policy is
mentioned for everyone else. When every policy has the day off there is
no post at all.
"""

import uuid
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.leave_policy import LeavePolicy
from app.models.leave_request import LeaveKind, LeaveRequest, LeaveStatus
from app.models.policy_holiday import HolidayKind
from app.repositories.leave_policy import LeavePolicyRepository
from app.repositories.leave_request import LeaveRequestRepository
from app.repositories.policy_holiday import PolicyHolidayRepository
from app.repositories.user import UserRepository
from app.services.leave.digest_compose import OutToday, compose

# How far ahead to look for someone's next working day.
LOOKAHEAD = timedelta(days=62)


@dataclass(frozen=True)
class _Calendar:
    """One policy's working days and mandatory holidays around today."""

    policy: LeavePolicy
    holidays: dict[date, str]

    def works(self, day: date) -> bool:
        return day.weekday() in self.policy.working_days and day not in self.holidays

    def next_working_day(self, after: date) -> date | None:
        day = after + timedelta(days=1)
        while day <= after + LOOKAHEAD:
            if self.works(day):
                return day
            day += timedelta(days=1)
        return None


async def build_digest(db: AsyncSession, org_id: uuid.UUID, today: date) -> str | None:
    """The day's post, or None when there's nobody to mention or nobody at work."""
    policies = await LeavePolicyRepository(db, org_id=org_id).list_ordered()
    requests = [
        r
        for r in await LeaveRequestRepository(db, org_id=org_id).active_between(None, today, today)
        if r.status == LeaveStatus.APPROVED
    ]
    latest_end = max((r.end_date for r in requests), default=today)
    calendars = await _calendars(db, org_id, policies, today, latest_end + LOOKAHEAD)
    working = [c for c in calendars.values() if c.works(today)]
    if not working:
        return None
    names = await UserRepository(db).get_names_by_ids({r.user_id for r in requests})
    away: list[OutToday] = []
    remote: list[OutToday] = []
    for request in requests:
        calendar = calendars.get(request.policy_id)
        if calendar is None or not calendar.works(today):
            continue
        person = _person(request, names, calendar)
        (remote if request.kind == LeaveKind.WFH else away).append(person)
    holidays = [
        f"{c.policy.name} ({c.holidays[today]})" for c in calendars.values() if today in c.holidays
    ]
    return compose(today, away, remote, holidays)


async def _calendars(
    db: AsyncSession, org_id: uuid.UUID, policies: list[LeavePolicy], start: date, end: date
) -> dict[uuid.UUID, _Calendar]:
    repo = PolicyHolidayRepository(db, org_id=org_id)
    calendars = {}
    for policy in policies:
        rows = await repo.list_between(policy.id, start, end, kind=HolidayKind.MANDATORY)
        calendars[policy.id] = _Calendar(policy, {row.date: row.name for row in rows})
    return calendars


def _person(request: LeaveRequest, names: dict[uuid.UUID, str], calendar: _Calendar) -> OutToday:
    return OutToday(
        name=names.get(request.user_id, "Someone"),
        half_day=request.half_day,
        back_on=calendar.next_working_day(request.end_date),
    )
