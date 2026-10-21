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
from datetime import timedelta
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
