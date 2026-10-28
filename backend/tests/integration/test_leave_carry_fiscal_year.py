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

"""Carry-forward follows each policy's own leave year, with fixed dates.

An April policy carries in the first week of April, a calendar policy in
the first week of January, and the days carried out of the old year never
turn leave already taken in it into loss of pay.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.leave_ledger import LeaveLedgerEntry, LedgerEntryType
from app.models.leave_request import LeaveRequest
from tests.integration.leave_carry_support import run, set_type
from tests.integration.leave_edge_support import add_policy, days_left, freeze_today, place
from tests.integration.leave_support import Factory, add_request, setup_org

pytestmark = pytest.mark.integration
D = Decimal


async def _carried(factory: Factory, user: uuid.UUID) -> list[tuple[int, Decimal]]:
    async with factory() as db:
        rows = await db.scalars(
            select(LeaveLedgerEntry).where(
                LeaveLedgerEntry.user_id == user,
                LeaveLedgerEntry.entry_type == LedgerEntryType.CARRY_FORWARD,
            )
        )
        return sorted((r.leave_year, r.days) for r in rows)


async def test_an_april_policy_carries_in_the_first_week_of_april(
    pg_session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    org, (emp,), _ = await setup_org(pg_session_factory, "Emp")
    policy, cl = await add_policy(pg_session_factory, org, "India", quota="18", year_start_month=4)
    await set_type(pg_session_factory, cl, carry_forward_days=D(5))
    await place(pg_session_factory, org, emp, policy)
    # Ten days in May 2029: the leave year running April 2029 to March 2030.
    await add_request(
        pg_session_factory, org, emp, date(2029, 5, 7), date(2029, 5, 18), "10", type_id=cl
    )
    assert await run(pg_session_factory, org, date(2030, 1, 1)) == 0
    assert await run(pg_session_factory, org, date(2030, 3, 31)) == 0
    assert await run(pg_session_factory, org, date(2030, 4, 8)) == 0
    assert await run(pg_session_factory, org, date(2030, 4, 7)) == 1
    assert await run(pg_session_factory, org, date(2030, 4, 1)) == 0  # already done
    assert await _carried(pg_session_factory, emp) == [(2029, D(-5)), (2030, D(5))]

    freeze_today(monkeypatch, date(2030, 4, 8))
    # 18 - 10 taken - 5 carried out; the new year starts at 18 + 5.
    assert await days_left(pg_session_factory, org, emp, 2029) == (D(3), D(0))
    assert await days_left(pg_session_factory, org, emp, 2030) == (D(23), D(0))
    async with pg_session_factory() as db:
        taken = (await db.scalars(select(LeaveRequest).where(LeaveRequest.user_id == emp))).one()
    assert taken.lop_days == 0


async def test_each_policy_carries_on_its_own_new_year(pg_session_factory: Factory) -> None:
    org, (jan_emp, apr_emp), casual = await setup_org(pg_session_factory, "Jan", "Apr")
    await set_type(pg_session_factory, casual, carry_forward_days=D(2))
    policy, cl = await add_policy(pg_session_factory, org, "April", year_start_month=4)
    await set_type(pg_session_factory, cl, carry_forward_days=D(2))
    await place(pg_session_factory, org, apr_emp, policy)
    # 1 Jan: only the calendar-year policy is due.
    assert await run(pg_session_factory, org, date(2030, 1, 2)) == 1
    assert await _carried(pg_session_factory, jan_emp) == [(2029, D(-2)), (2030, D(2))]
    assert await _carried(pg_session_factory, apr_emp) == []
    # 1 Apr: only the April policy.
    assert await run(pg_session_factory, org, date(2030, 4, 2)) == 1
    assert await _carried(pg_session_factory, apr_emp) == [(2029, D(-2)), (2030, D(2))]
    assert len(await _carried(pg_session_factory, jan_emp)) == 2
