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

"""Leave already under way: the days taken stay, only the rest moves or goes."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.leave_request import LeaveRequest
from app.models.notification import Notification
from app.models.policy_holiday import HolidayKind, PolicyHoliday
from app.services.leave.policies import ensure_default_policy
from tests.integration.leave_support import Factory, add_request, as_user, team

pytestmark = pytest.mark.integration


async def _notes_for(factory: Factory, user: uuid.UUID) -> list[str]:
    async with factory() as db:
        rows = await db.scalars(select(Notification.title).where(Notification.user_id == user))
        return list(rows)


async def _under_way(factory: Factory, org: uuid.UUID, user: uuid.UUID, casual: uuid.UUID,
                     start: date, end: date, days: str, mgr: uuid.UUID) -> str:  # fmt: skip
    await add_request(
        factory, org, user, start, end, days, type_id=casual,
        decided_by=mgr, decided_at=datetime.now(UTC),
    )  # fmt: skip
    async with factory() as db:
        found = await db.scalars(
            select(LeaveRequest.id).where(
                LeaveRequest.user_id == user, LeaveRequest.start_date == start
            )
        )
        return str(found.one())


async def test_leave_under_way_keeps_the_days_taken(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, p, casual = await team(pg_session_factory)
    today = datetime.now(UTC).date()
    start = today - timedelta(days=3)
    end = today + timedelta(days=3)
    await add_request(
        pg_session_factory, org, p["emp"], start, end, "5", type_id=casual,
        decided_by=p["mgr"], decided_at=datetime.now(UTC),
    )  # fmt: skip
    async with pg_session_factory() as db:
        rid = (
            await db.scalars(select(LeaveRequest.id).where(LeaveRequest.user_id == p["emp"]))
        ).one()
    headers = as_user(p["hr"], org)

    moved_start = await client.post(
        f"/api/v1/leave/requests/{rid}/reschedule",
        json={"start_date": today.isoformat(), "end_date": end.isoformat()},
        headers=headers,
    )
    assert moved_start.status_code == 422  # started: only the end can move
    ended = await client.post(
        f"/api/v1/leave/requests/{rid}/withdraw",
        json={"note": "Needed back"},
        headers=headers,
    )
    assert ended.status_code == 200, ended.text
    assert ended.json()["status"] == "approved"
    assert ended.json()["end_date"] == (today - timedelta(days=1)).isoformat()
    assert "Leave ended early" in await _notes_for(pg_session_factory, p["emp"])


async def test_started_leave_extends_within_the_year_but_not_past_it(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, p, casual = await team(pg_session_factory)
    today = datetime.now(UTC).date()
    # Started yesterday and runs to the end of the week after next.
    start = today - timedelta(days=1)
    end = today + timedelta(days=1)
    rid = await _under_way(pg_session_factory, org, p["emp"], casual, start, end, "1", p["mgr"])
    headers = as_user(p["mgr"], org)

    next_year = date(today.year + 1, 1, 5)
    crossing = await client.post(
        f"/api/v1/leave/requests/{rid}/reschedule",
        json={"start_date": start.isoformat(), "end_date": next_year.isoformat()},
        headers=headers,
    )
    assert crossing.status_code == 422, crossing.text
    assert "leave year" in crossing.json()["detail"]

    longer = end + timedelta(days=7)
    extended = await client.post(
        f"/api/v1/leave/requests/{rid}/reschedule",
        json={"start_date": start.isoformat(), "end_date": longer.isoformat()},
        headers=headers,
    )
    assert extended.status_code == 200, extended.text
    assert extended.json()["end_date"] == longer.isoformat()
    # The days already booked stay counted; the added working days come on top.
    assert float(extended.json()["days"]) > 1


async def test_shortening_started_leave_to_only_days_off_is_refused(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, p, casual = await team(pg_session_factory)
    today = datetime.now(UTC).date()
    yesterday = today - timedelta(days=1)
    rid = await _under_way(
        pg_session_factory, org, p["emp"], casual, yesterday, today + timedelta(days=3), "3",
        p["mgr"],
    )  # fmt: skip
    # Yesterday and today are company holidays: shortening to them leaves nothing.
    async with pg_session_factory() as db:
        policy = await ensure_default_policy(db, org)
        for day in (yesterday, today):
            db.add(PolicyHoliday(
                org_id=org, policy_id=policy.id, date=day, name="Holiday",
                kind=HolidayKind.MANDATORY,
            ))  # fmt: skip
        await db.commit()
    cut = await client.post(
        f"/api/v1/leave/requests/{rid}/reschedule",
        json={"start_date": yesterday.isoformat(), "end_date": today.isoformat()},
        headers=as_user(p["mgr"], org),
    )
    assert cut.status_code == 422, cut.text
    assert "weekends or holidays" in cut.json()["detail"]
