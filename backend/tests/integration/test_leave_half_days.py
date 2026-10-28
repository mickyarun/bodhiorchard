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

"""Half days against the balance, overlaps and the WFH allowance (today frozen)."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.models.leave_policy import WfhApproval
from app.models.leave_request import HalfDay, LeaveKind, LeaveStatus
from app.schemas.leave import LeaveRequestCreate
from app.services.leave.cancellation import cancel
from app.services.leave.evaluation import evaluate
from app.services.leave.lifecycle import submit
from app.services.leave.policies import resolve_member_policy
from tests.integration.leave_edge_support import days_left, freeze_today
from tests.integration.leave_support import Factory, leave_body, report_to, setup_org

pytestmark = pytest.mark.integration
D = Decimal
TODAY = date(2030, 6, 3)  # a Monday
TUE, WED = date(2030, 6, 11), date(2030, 6, 12)
AM, PM = HalfDay.FIRST_HALF, HalfDay.SECOND_HALF


@pytest.fixture(autouse=True)
def _frozen(monkeypatch: pytest.MonkeyPatch) -> None:
    freeze_today(monkeypatch, TODAY)


async def _team(factory: Factory) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    org, (emp, mgr), casual = await setup_org(factory, "Emp", "Mgr")
    await report_to(factory, org, emp, mgr)
    return org, emp, casual


async def _problems(
    factory: Factory, org: uuid.UUID, emp: uuid.UUID, body: LeaveRequestCreate
) -> list[str]:
    async with factory() as db:
        member = await resolve_member_policy(db, org, emp)
        result = await evaluate(db, member=member, user_id=emp, body=body)
        return [p.code for p in result.problems]


async def _send(
    factory: Factory, org: uuid.UUID, emp: uuid.UUID, body: LeaveRequestCreate
) -> tuple[uuid.UUID, Decimal, Decimal, LeaveStatus]:
    async with factory() as db:
        request, _ = await submit(db, org, emp, body)
        await db.commit()
        return request.id, request.days, request.lop_days, request.status


async def test_a_half_day_clashes_with_the_same_half_and_any_wider_leave(
    pg_session_factory: Factory,
) -> None:
    org, emp, casual = await _team(pg_session_factory)
    _, days, _, _ = await _send(
        pg_session_factory, org, emp, leave_body(casual, TUE, TUE, half_day=AM)
    )
    assert days == D("0.5")
    clashing = (
        leave_body(casual, TUE, TUE, half_day=AM),
        leave_body(casual, TUE, TUE),
        leave_body(casual, date(2030, 6, 10), WED),
    )
    for body in clashing:
        assert await _problems(pg_session_factory, org, emp, body) == ["overlap"], body
    assert (
        await _problems(pg_session_factory, org, emp, leave_body(casual, TUE, TUE, half_day=PM))
        == []
    )


async def test_two_halves_cost_a_day_and_cancelling_one_gives_half_back(
    pg_session_factory: Factory,
) -> None:
    org, emp, casual = await _team(pg_session_factory)
    morning, *_ = await _send(
        pg_session_factory, org, emp, leave_body(casual, TUE, TUE, half_day=AM)
    )
    await _send(pg_session_factory, org, emp, leave_body(casual, TUE, TUE, half_day=PM))
    assert await days_left(pg_session_factory, org, emp, 2030) == (D(4), D(0))
    async with pg_session_factory() as db:
        await cancel(db, org, emp, morning)
        await db.commit()
    assert await days_left(pg_session_factory, org, emp, 2030) == (D("4.5"), D(0))
    # The freed morning can be booked again.
    assert (
        await _problems(pg_session_factory, org, emp, leave_body(casual, TUE, TUE, half_day=AM))
        == []
    )


async def test_the_last_half_day_of_balance_pays_half_of_a_full_day(
    pg_session_factory: Factory,
) -> None:
    org, emp, casual = await _team(pg_session_factory)
    # Mon to Thu plus Friday morning: 4.5 of the 5 days.
    await _send(
        pg_session_factory, org, emp, leave_body(casual, date(2030, 6, 10), date(2030, 6, 13))
    )
    friday = date(2030, 6, 14)
    await _send(pg_session_factory, org, emp, leave_body(casual, friday, friday, half_day=AM))
    assert await days_left(pg_session_factory, org, emp, 2030) == (D("0.5"), D(0))
    monday = date(2030, 6, 17)
    _, days, lop, _ = await _send(pg_session_factory, org, emp, leave_body(casual, monday, monday))
    assert (days, lop) == (D(1), D("0.5"))
    # Nothing left: a further half day is all loss of pay, and days left stay at zero.
    tuesday = date(2030, 6, 18)
    _, days, lop, _ = await _send(
        pg_session_factory, org, emp, leave_body(casual, tuesday, tuesday, half_day=PM)
    )
    assert (days, lop) == (D("0.5"), D("0.5"))
    assert await days_left(pg_session_factory, org, emp, 2030) == (D(0), D(1))


async def test_half_day_wfh_uses_half_of_the_monthly_allowance(
    pg_session_factory: Factory,
) -> None:
    org, emp, _ = await _team(pg_session_factory)
    async with pg_session_factory() as db:
        policy = (await resolve_member_policy(db, org, emp)).policy
        policy.wfh_approval, policy.wfh_monthly_auto_days = WfhApproval.AUTO_WITHIN_ALLOWANCE, 1
        await db.commit()

    def wfh(day: date, half: HalfDay = HalfDay.NONE) -> LeaveRequestCreate:
        return LeaveRequestCreate(kind=LeaveKind.WFH, start_date=day, end_date=day, half_day=half)

    # Two halves fill the one-day allowance; a third half goes to the manager.
    assert (await _send(pg_session_factory, org, emp, wfh(TUE, AM)))[3] == LeaveStatus.APPROVED
    assert (await _send(pg_session_factory, org, emp, wfh(TUE, PM)))[3] == LeaveStatus.APPROVED
    assert (await _send(pg_session_factory, org, emp, wfh(WED, AM)))[3] == LeaveStatus.PENDING
    # July is still empty: its Monday alone would be approved at once ...
    async with pg_session_factory() as db:
        member = await resolve_member_policy(db, org, emp)
        alone = await evaluate(db, member=member, user_id=emp, body=wfh(date(2030, 7, 1)))
    assert alone.auto_approved and not alone.problems
    # ... but the same Monday with June's last Friday goes to the manager whole,
    # since June is used up.
    across = LeaveRequestCreate(
        kind=LeaveKind.WFH, start_date=date(2030, 6, 28), end_date=date(2030, 7, 1)
    )
    assert (await _send(pg_session_factory, org, emp, across))[3] == LeaveStatus.PENDING
    # The allowance is per calendar month: an empty August starts afresh.
    august = date(2030, 8, 6)
    assert (await _send(pg_session_factory, org, emp, wfh(august)))[3] == LeaveStatus.APPROVED
