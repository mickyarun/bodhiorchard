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

"""Leave years end where the policy says: Dec 31, Mar 31, and leap days in between.

Every test pins "today", so the dates are real calendar dates.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.models.leave_type import LeaveAccrual
from app.services.leave.evaluation import evaluate
from app.services.leave.evaluation_steps import Evaluation
from app.services.leave.lifecycle import submit
from app.services.leave.policies import resolve_member_policy
from tests.integration.leave_edge_support import (
    add_holiday,
    add_policy,
    days_left,
    freeze_today,
    place,
)
from tests.integration.leave_support import Factory, leave_body, report_to, setup_org

pytestmark = pytest.mark.integration
D = Decimal


async def _member(
    factory: Factory,
    *,
    year_start_month: int = 1,
    quota: str = "5",
    accrual: LeaveAccrual = LeaveAccrual.UPFRONT,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    """``(org, emp, policy, type)``: emp on a fresh policy with one leave type."""
    org, (emp, mgr), _ = await setup_org(factory, "Emp", "Mgr")
    await report_to(factory, org, emp, mgr)
    policy_id, type_id = await add_policy(
        factory, org, "Edge", quota=quota, accrual=accrual, year_start_month=year_start_month
    )
    await place(factory, org, emp, policy_id)
    return org, emp, policy_id, type_id


async def _preview(
    factory: Factory, org: uuid.UUID, emp: uuid.UUID, type_id: uuid.UUID, start: date, end: date
) -> Evaluation:
    async with factory() as db:
        member = await resolve_member_policy(db, org, emp)
        return await evaluate(db, member=member, user_id=emp, body=leave_body(type_id, start, end))


async def _book(
    factory: Factory, org: uuid.UUID, emp: uuid.UUID, type_id: uuid.UUID, start: date, end: date
) -> tuple[Decimal, Decimal]:
    async with factory() as db:
        request, _ = await submit(db, org, emp, leave_body(type_id, start, end))
        await db.commit()
        return request.days, request.lop_days


def _codes(result: Evaluation) -> list[str]:
    return [p.code for p in result.problems]


async def test_dec_31_and_jan_2_draw_on_different_years(
    pg_session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    freeze_today(monkeypatch, date(2030, 12, 16))
    org, emp, _policy, cl = await _member(pg_session_factory)
    eve, new_year, jan_2 = date(2030, 12, 31), date(2031, 1, 1), date(2031, 1, 2)
    assert _codes(await _preview(pg_session_factory, org, emp, cl, eve, new_year)) == [
        "crosses_leave_year"
    ]
    assert await _book(pg_session_factory, org, emp, cl, eve, eve) == (D(1), D(0))
    assert await _book(pg_session_factory, org, emp, cl, jan_2, jan_2) == (D(1), D(0))
    assert await days_left(pg_session_factory, org, emp, 2030) == (D(4), D(0))
    assert await days_left(pg_session_factory, org, emp, 2031) == (D(4), D(0))
    # Requests reach to the end of next leave year and not a day further.
    last = date(2031, 12, 31)
    assert _codes(await _preview(pg_session_factory, org, emp, cl, last, last)) == []
    after = date(2032, 1, 1)
    assert _codes(await _preview(pg_session_factory, org, emp, cl, after, after)) == [
        "too_far_ahead"
    ]


async def test_an_april_leave_year_splits_at_march_31(
    pg_session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    freeze_today(monkeypatch, date(2030, 3, 11))
    org, emp, _policy, cl = await _member(pg_session_factory, year_start_month=4)
    friday, monday = date(2030, 3, 29), date(2030, 4, 1)
    across = await _preview(pg_session_factory, org, emp, cl, friday, monday)
    assert _codes(across) == ["crosses_leave_year"]
    assert "Sun 31 Mar" in across.problems[0].message
    # Four days in March use up the 2029 year; April starts the 2030 one in full.
    assert await _book(pg_session_factory, org, emp, cl, date(2030, 3, 25), date(2030, 3, 28)) == (
        D(4),
        D(0),
    )
    assert await _book(pg_session_factory, org, emp, cl, friday, friday) == (D(1), D(0))
    assert _codes(await _preview(pg_session_factory, org, emp, cl, friday, friday)) == ["overlap"]
    assert await _book(pg_session_factory, org, emp, cl, monday, monday) == (D(1), D(0))
    assert await days_left(pg_session_factory, org, emp, 2029) == (D(0), D(0))
    assert await days_left(pg_session_factory, org, emp, 2030) == (D(4), D(0))
    # Next leave year ends on 31 Mar 2031.
    end = date(2031, 3, 31)
    assert _codes(await _preview(pg_session_factory, org, emp, cl, end, end)) == []
    beyond = date(2031, 4, 1)
    assert _codes(await _preview(pg_session_factory, org, emp, cl, beyond, beyond)) == [
        "too_far_ahead"
    ]


async def test_monthly_accrual_starts_again_on_january_1(
    pg_session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    freeze_today(monkeypatch, date(2030, 12, 16))
    org, emp, _policy, cl = await _member(
        pg_session_factory, quota="12", accrual=LeaveAccrual.MONTHLY
    )
    # By Dec 31 the whole year has been earned; Jan 2 only has January's day.
    assert await _book(
        pg_session_factory, org, emp, cl, date(2030, 12, 30), date(2030, 12, 31)
    ) == (
        D(2),
        D(0),
    )
    assert await _book(pg_session_factory, org, emp, cl, date(2031, 1, 2), date(2031, 1, 3)) == (
        D(2),
        D(1),
    )
    assert await days_left(pg_session_factory, org, emp, 2031) == (D(0), D(1))


async def test_a_leap_day_is_a_working_day_unless_it_is_a_holiday(
    pg_session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    freeze_today(monkeypatch, date(2028, 2, 14))
    org, emp, policy, cl = await _member(
        pg_session_factory, quota="12", accrual=LeaveAccrual.MONTHLY
    )
    mon, leap, wed = date(2028, 2, 28), date(2028, 2, 29), date(2028, 3, 1)
    span = await _preview(pg_session_factory, org, emp, cl, mon, wed)
    assert (span.days, span.excluded) == (D(3), [])
    # Priced on what is earned by February: 2 of the 12.
    assert (span.balance_before, span.lop_days) == (D(2), D(1))
    await add_holiday(pg_session_factory, org, policy, leap, "Leap holiday")
    again = await _preview(pg_session_factory, org, emp, cl, mon, wed)
    assert (again.days, again.excluded, again.lop_days) == (D(2), [(leap, "Leap holiday")], D(0))
