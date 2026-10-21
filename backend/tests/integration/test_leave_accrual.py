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

"""A monthly leave type prices requests on what is earned by their start date."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient

from app.models.leave_type import LeaveAccrual, LeaveType
from app.services.leave.balance_after import balances_after
from app.services.leave.evaluation import evaluate
from app.services.leave.lifecycle import submit
from app.services.leave.policies import resolve_member_policy, today_for
from app.services.leave.summary import build_summary
from tests.integration.leave_support import (
    Factory,
    as_user,
    future_monday,
    give_role,
    leave_body,
    report_to,
    setup_org,
)

pytestmark = pytest.mark.integration
D = Decimal
# 1.2 a year is 0.1 a month, so what's earned by a date is 0.1 x its month.
QUOTA = D("1.2")


async def _make_monthly(
    factory: Factory, type_id: uuid.UUID, accrual: LeaveAccrual, *, encashable: bool = False
) -> None:
    async with factory() as db:
        leave_type = await db.get(LeaveType, type_id)
        assert leave_type is not None
        leave_type.annual_quota_days = QUOTA
        leave_type.accrual = accrual
        leave_type.is_encashable = encashable
        await db.commit()


@pytest.mark.parametrize(
    ("accrual", "monthly"), [(LeaveAccrual.MONTHLY, True), (LeaveAccrual.UPFRONT, False)]
)
async def test_requests_are_priced_on_what_is_earned_by_their_start(
    pg_session_factory: Factory, accrual: LeaveAccrual, monthly: bool
) -> None:
    org, (emp, mgr), casual = await setup_org(pg_session_factory, "Emp", "Mgr")
    await report_to(pg_session_factory, org, emp, mgr)
    await _make_monthly(pg_session_factory, casual, accrual)
    mon = future_monday()
    earned = D("0.1") * mon.month if monthly else QUOTA
    async with pg_session_factory() as db:
        member = await resolve_member_policy(db, org, emp)
        body = leave_body(casual, mon, mon + timedelta(days=1))
        preview = await evaluate(db, member=member, user_id=emp, body=body)
        assert preview.problems == []
        assert preview.balance_before == earned
        assert preview.lop_days == D(2) - earned
        request, _ = await submit(db, org, emp, body)
        await db.commit()
        assert request.lop_days == D(2) - earned
        # The approver's card prices it the same way, on its start date: the
        # earned days are used up and the rest is loss of pay, not a debt.
        after = (await balances_after(db, org, [request]))[request.id]
        assert after.days == 0


async def test_the_leave_page_shows_what_is_earned_so_far(pg_session_factory: Factory) -> None:
    org, (emp,), casual = await setup_org(pg_session_factory, "Emp")
    await _make_monthly(pg_session_factory, casual, LeaveAccrual.MONTHLY)
    async with pg_session_factory() as db:
        summary = await build_summary(db, org, emp, None)
        member = await resolve_member_policy(db, org, emp)
    [balance] = summary.balances
    month = today_for(member.policy).month
    assert balance.accrual == LeaveAccrual.MONTHLY
    assert (balance.allocated, balance.earned) == (QUOTA, D("0.1") * month)
    assert balance.available == D("0.1") * month


async def test_the_balances_report_shows_what_is_encashable_at_exit(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, (hr, emp), casual = await setup_org(pg_session_factory, "Hr", "Emp")
    await give_role(pg_session_factory, org, hr, "hr")
    await _make_monthly(pg_session_factory, casual, LeaveAccrual.MONTHLY, encashable=True)
    r = await client.get("/api/v1/leave/reports/balances", headers=as_user(hr, org))
    assert r.status_code == 200, r.text
    row = next(x for x in r.json()["rows"] if x["user_id"] == str(emp))
    async with pg_session_factory() as db:
        month = today_for((await resolve_member_policy(db, org, emp)).policy).month
    # Nothing used: everything earned so far would be paid out.
    assert D(row["encashable"]) == D(row["available"]) == D("0.1") * month
    assert (D(row["allocated"]), D(row["earned"])) == (QUOTA, D("0.1") * month)
    csv = await client.get("/api/v1/leave/reports/balances.csv", headers=as_user(hr, org))
    header = csv.content.decode("utf-8-sig").splitlines()[0]
    assert "Earned so far" in header and "Encashable at exit" in header


def _first_monday(year: int, month: int) -> date:
    first = date(year, month, 1)
    return first + timedelta(days=(7 - first.weekday()) % 7)


@pytest.mark.parametrize("december_first", [True, False])
async def test_booking_order_never_changes_what_is_paid(
    pg_session_factory: Factory, december_first: bool
) -> None:
    """18 a year monthly: 10 December days and 3 February days are all paid,
    whichever is booked first (next year, so every date is still ahead)."""
    org, (emp, mgr), casual = await setup_org(pg_session_factory, "Emp", "Mgr")
    await report_to(pg_session_factory, org, emp, mgr)
    async with pg_session_factory() as db:
        leave_type = await db.get(LeaveType, casual)
        assert leave_type is not None
        leave_type.annual_quota_days, leave_type.accrual = D(18), LeaveAccrual.MONTHLY
        await db.commit()
    year = date.today().year + 1
    dec, feb = _first_monday(year, 12), _first_monday(year, 2)
    bodies = [
        leave_body(casual, dec, dec + timedelta(days=11)),  # two working weeks
        leave_body(casual, feb, feb + timedelta(days=2)),  # Mon to Wed
    ]
    async with pg_session_factory() as db:
        made = []
        for body in bodies if december_first else bodies[::-1]:
            request, _ = await submit(db, org, emp, body)
            made.append(request)
        await db.commit()
    assert sorted((r.days, r.lop_days) for r in made) == [(D(3), D(0)), (D(10), D(0))]


async def test_how_a_type_is_given_is_locked_once_this_year_is_in_use(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, (hr, emp), casual = await setup_org(pg_session_factory, "Hr", "Emp")
    await give_role(pg_session_factory, org, hr, "hr")
    url = f"/api/v1/leave/types/{casual}"
    body = {"name": "Casual", "code": "CL", "annual_quota_days": "5", "accrual": "monthly"}
    # Nobody has used it yet: it can switch freely.
    assert (await client.put(url, json=body, headers=as_user(hr, org))).status_code == 200
    body["accrual"] = "upfront"
    assert (await client.put(url, json=body, headers=as_user(hr, org))).status_code == 200
    mon = future_monday()
    async with pg_session_factory() as db:
        await submit(db, org, emp, leave_body(casual, mon, mon))
        await db.commit()
    body["accrual"] = "monthly"
    refused = await client.put(url, json=body, headers=as_user(hr, org))
    assert refused.status_code == 409, refused.text
    # Other edits still go through.
    body["accrual"], body["name"] = "upfront", "Casual leave"
    assert (await client.put(url, json=body, headers=as_user(hr, org))).status_code == 200
