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

"""Half days that share a date, and optional holidays people have booked."""

from __future__ import annotations

from datetime import timedelta

import pytest
from httpx import AsyncClient

from app.models.leave_request import HalfDay, LeaveKind
from app.models.policy_holiday import HolidayKind, PolicyHoliday
from app.repositories.policy_holiday import PolicyHolidayRepository
from app.schemas.leave import LeaveRequestCreate
from app.services.leave.evaluation import evaluate
from app.services.leave.lifecycle import submit
from app.services.leave.policies import resolve_member_policy
from tests.integration.leave_support import (
    Factory,
    as_user,
    future_monday,
    give_role,
    leave_body,
    month_mondays,
    report_to,
    setup_org,
)

pytestmark = pytest.mark.integration


async def test_a_morning_and_an_afternoon_dont_clash(pg_session_factory: Factory) -> None:
    org, (emp, mgr), casual = await setup_org(pg_session_factory, "Emp", "Mgr")
    await report_to(pg_session_factory, org, emp, mgr)
    tue = future_monday() + timedelta(days=1)
    async with pg_session_factory() as db:
        await submit(db, org, emp, leave_body(casual, tue, tue, half_day=HalfDay.FIRST_HALF))
        await db.commit()
        member = await resolve_member_policy(db, org, emp)
        afternoon = LeaveRequestCreate(
            kind=LeaveKind.WFH, start_date=tue, end_date=tue, half_day=HalfDay.SECOND_HALF
        )
        morning = afternoon.model_copy(update={"half_day": HalfDay.FIRST_HALF})
        whole_day = afternoon.model_copy(update={"half_day": HalfDay.NONE})
        codes = [
            [p.code for p in (await evaluate(db, member=member, user_id=emp, body=b)).problems]
            for b in (afternoon, morning, whole_day)
        ]
    assert codes == [[], ["overlap"], ["overlap"]]


async def test_a_booked_optional_holiday_keeps_its_date(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, (emp, mgr, hr), _ = await setup_org(pg_session_factory, "Emp", "Mgr", "Hr")
    await report_to(pg_session_factory, org, emp, mgr)
    await give_role(pg_session_factory, org, hr, "hr")
    day = month_mondays()[0]
    async with pg_session_factory() as db:
        policy = (await resolve_member_policy(db, org, emp)).policy
        policy.optional_holiday_quota = 1
        holiday = await PolicyHolidayRepository(db, org_id=org).create(
            PolicyHoliday(
                org_id=org, policy_id=policy.id, date=day, name="Onam", kind=HolidayKind.OPTIONAL
            )
        )
        await db.commit()
        booking = LeaveRequestCreate(
            kind=LeaveKind.OPTIONAL_HOLIDAY, holiday_id=holiday.id, start_date=day, end_date=day
        )
        await submit(db, org, emp, booking)
        await db.commit()
    url = f"/api/v1/leave/holidays/{holiday.id}"
    headers = as_user(hr, org)
    moved = {"date": (day + timedelta(days=1)).isoformat(), "name": "Onam", "kind": "optional"}
    assert (await client.put(url, json=moved, headers=headers)).status_code == 409
    mandatory = {"date": day.isoformat(), "name": "Onam", "kind": "mandatory"}
    assert (await client.put(url, json=mandatory, headers=headers)).status_code == 409
    assert (await client.delete(url, headers=headers)).status_code == 409
    renamed = {"date": day.isoformat(), "name": "Thiruvonam", "kind": "optional"}
    response = await client.put(url, json=renamed, headers=headers)
    assert response.status_code == 200 and response.json()["name"] == "Thiruvonam"
