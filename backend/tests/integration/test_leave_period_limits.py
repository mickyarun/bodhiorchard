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

"""Period leave's monthly limit at the edges: half days, two months, what counts."""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest
from httpx import AsyncClient

from app.models.leave_request import HalfDay, LeaveStatus
from app.services.leave.cancellation import cancel
from app.services.leave.errors import LeaveConflictError
from app.services.leave.lifecycle import submit
from tests.integration.leave_support import (
    Factory,
    as_user,
    leave_body,
    month_mondays,
    report_to,
    setup_org,
)
from tests.integration.period_support import add_period_leave

pytestmark = pytest.mark.integration
FULL = "already have 1 day booked"


def _weekday_back(day: date) -> date:
    while day.weekday() > 4:
        day -= timedelta(days=1)
    return day


def _weekday_on(day: date) -> date:
    while day.weekday() > 4:
        day += timedelta(days=1)
    return day


async def test_two_halves_fill_the_day_and_a_third_is_refused(
    pg_session_factory: Factory,
) -> None:
    org, (woman,), _ = await setup_org(pg_session_factory, "Asha")
    period = await add_period_leave(pg_session_factory, org, woman)
    mon, next_mon, _ = month_mondays()
    async with pg_session_factory() as db:
        for half in (HalfDay.FIRST_HALF, HalfDay.SECOND_HALF):
            request, _ = await submit(db, org, woman, leave_body(period, mon, mon, half_day=half))
            await db.commit()
            assert request.status == LeaveStatus.APPROVED and request.days == 0.5
        with pytest.raises(LeaveConflictError, match=FULL):
            body = leave_body(period, next_mon, next_mon, half_day=HalfDay.FIRST_HALF)
            await submit(db, org, woman, body)


async def test_last_and_first_working_days_of_two_months_count_one_each(
    pg_session_factory: Factory,
) -> None:
    org, (woman,), _ = await setup_org(pg_session_factory, "Asha")
    period = await add_period_leave(pg_session_factory, org, woman)
    # Two months inside one leave year (never December into January).
    month = next(m for m in (month_mondays(n)[0].replace(day=1) for n in (1, 2)) if m.month != 12)
    next_month = (month + timedelta(days=32)).replace(day=1)
    last = _weekday_back(next_month - timedelta(days=1))
    first = _weekday_on(next_month)
    async with pg_session_factory() as db:
        request, _ = await submit(db, org, woman, leave_body(period, last, first))
        await db.commit()
        assert request.status == LeaveStatus.APPROVED and request.days == 2


async def test_a_weekend_inside_the_range_is_not_counted(pg_session_factory: Factory) -> None:
    org, (woman,), _ = await setup_org(pg_session_factory, "Asha")
    period = await add_period_leave(pg_session_factory, org, woman)
    mon = month_mondays()[1]
    saturday = mon - timedelta(days=2)
    async with pg_session_factory() as db:
        request, _ = await submit(db, org, woman, leave_body(period, saturday, mon))
        await db.commit()
        assert request.status == LeaveStatus.APPROVED and request.days == 1


async def test_cancelling_frees_the_month(pg_session_factory: Factory) -> None:
    org, (woman,), _ = await setup_org(pg_session_factory, "Asha")
    period = await add_period_leave(pg_session_factory, org, woman)
    mon, next_mon, _ = month_mondays()
    async with pg_session_factory() as db:
        request, _ = await submit(db, org, woman, leave_body(period, mon, mon))
        await db.commit()
        await cancel(db, org, woman, request.id)
        await db.commit()
        again, _ = await submit(db, org, woman, leave_body(period, next_mon, next_mon))
        await db.commit()
        assert again.status == LeaveStatus.APPROVED


async def test_other_leave_and_wfh_do_not_use_it_up(pg_session_factory: Factory) -> None:
    org, (woman, mgr), casual = await setup_org(pg_session_factory, "Asha", "Mgr")
    await report_to(pg_session_factory, org, woman, mgr)
    period = await add_period_leave(pg_session_factory, org, woman)
    mon = month_mondays()[0]
    async with pg_session_factory() as db:
        await submit(db, org, woman, leave_body(casual, mon, mon))
        await db.commit()
        request, _ = await submit(
            db, org, woman, leave_body(period, mon + timedelta(days=1), mon + timedelta(days=1))
        )
        await db.commit()
        assert request.status == LeaveStatus.APPROVED


async def test_preview_says_why_and_never_promises_with_a_problem(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, (woman, man), _ = await setup_org(pg_session_factory, "Asha", "Ravi")
    period = await add_period_leave(pg_session_factory, org, woman)
    mon, next_mon, _ = month_mondays()

    async def preview(who: uuid.UUID, day: date) -> dict[str, object]:
        body = {"kind": "leave", "leave_type_id": str(period), "start_date": day.isoformat(),
                "end_date": day.isoformat()}  # fmt: skip
        r = await client.post(
            "/api/v1/leave/requests/preview", json=body, headers=as_user(who, org)
        )
        assert r.status_code == 200, r.text
        return r.json()  # type: ignore[no-any-return]

    clean = await preview(woman, mon)
    assert clean["auto_approved"] is True and clean["problems"] == []
    # To someone it isn't for, it looks like any type not on their policy.
    his = await preview(man, mon)
    assert [p["code"] for p in his["problems"]][:1] == ["inactive_type"]
    async with pg_session_factory() as db:
        await submit(db, org, woman, leave_body(period, mon, mon))
        await db.commit()
    full = await preview(woman, next_mon)
    assert [p["code"] for p in full["problems"]] == ["monthly_limit"]
    assert full["auto_approved"] is False
