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

"""Carrying unused leave into the new leave year."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select

from app.models.employee_profile import EmployeeStatus
from app.models.leave_ledger import LedgerEntryType
from app.models.leave_policy import LeavePolicy
from app.models.leave_request import LeaveRequest, LeaveStatus
from app.repositories.employee_profile import EmployeeProfileRepository
from app.repositories.leave_ledger import LeaveLedgerRepository
from tests.integration.leave_carry_support import (
    NEW,
    OLD,
    D,
    add_type,
    carried,
    entries,
    policy_of,
    run,
    set_type,
)
from tests.integration.leave_support import Factory, add_request, setup_org

pytestmark = pytest.mark.integration


async def test_unused_days_carry_up_to_the_cap_once(pg_session_factory: Factory) -> None:
    org, (rested, busy, unpaid), casual = await setup_org(
        pg_session_factory, "Rested", "Busy", "Unpaid"
    )
    await set_type(pg_session_factory, casual, annual_quota_days=D(18), carry_forward_days=D(5))
    may, june = date(OLD, 5, 4), date(OLD, 6, 1)
    await add_request(pg_session_factory, org, rested, may, may, "10", type_id=casual)
    await add_request(pg_session_factory, org, busy, may, may, "15", type_id=casual)
    await add_request(
        pg_session_factory, org, busy, june, june, "1", type_id=casual, status=LeaveStatus.PENDING
    )
    # 16 days off, 2 of them loss of pay: only the 14 paid ones used the balance.
    await add_request(pg_session_factory, org, unpaid, may, may, "16", type_id=casual, lop="2")

    assert await run(pg_session_factory, org, date(NEW, 1, 1)) == 3
    assert await carried(pg_session_factory, rested) == [(casual, NEW, D(5))]
    assert await carried(pg_session_factory, busy) == [(casual, NEW, D(2))]
    assert await carried(pg_session_factory, unpaid) == [(casual, NEW, D(4))]
    # The days move: out of the old year and into the new, each row noted and
    # shown in their ledger as "Automatic".
    moves = await entries(pg_session_factory, rested, LedgerEntryType.CARRY_FORWARD)
    assert sorted((e.leave_year, e.days, e.note, e.created_by) for e in moves) == [
        (OLD, D(-5), f"Carried forward to {NEW}", None),
        (NEW, D(5), f"Carried forward from {OLD}", None),
    ]
    async with pg_session_factory() as db:
        # What's left of the old year (8 unused, 5 moved) can't pay twice.
        totals = await LeaveLedgerRepository(db, org_id=org).totals(rested, OLD)
        assert totals[casual] == (D(18), D(0), D(-5))
    # The old year's allocation the carry was worked out from is now fixed.
    frozen = await entries(pg_session_factory, rested, LedgerEntryType.ALLOCATION)
    assert [(e.leave_year, e.days) for e in frozen] == [(OLD, D(18))]

    # Another pass the same week (another worker, the next tick) adds nothing.
    assert await run(pg_session_factory, org, date(NEW, 1, 3)) == 0
    assert await carried(pg_session_factory, rested) == [(casual, NEW, D(5))]


async def test_runs_only_in_the_first_week_of_the_leave_year(pg_session_factory: Factory) -> None:
    org, (emp,), casual = await setup_org(pg_session_factory, "Emp")
    await set_type(pg_session_factory, casual, carry_forward_days=D(5))
    assert await run(pg_session_factory, org, date(OLD, 12, 31)) == 0
    assert await run(pg_session_factory, org, date(NEW, 1, 8)) == 0
    assert await run(pg_session_factory, org, date(NEW, 1, 7)) == 1
    assert await carried(pg_session_factory, emp) == [(casual, NEW, D(5))]


async def test_types_without_a_cap_or_switched_off_carry_nothing(
    pg_session_factory: Factory,
) -> None:
    org, (emp,), casual = await setup_org(pg_session_factory, "Emp")
    policy = await policy_of(pg_session_factory, casual)
    await add_type(pg_session_factory, policy, "OL", annual_quota_days=D(10),
                    carry_forward_days=D(5), is_active=False)  # fmt: skip
    assert await run(pg_session_factory, org, date(NEW, 1, 1)) == 0
    await set_type(pg_session_factory, casual, carry_forward_days=D(3))
    assert await run(pg_session_factory, org, date(NEW, 1, 1)) == 1
    assert await carried(pg_session_factory, emp) == [(casual, NEW, D(3))]


async def test_a_type_added_in_the_new_year_has_nothing_to_carry(
    pg_session_factory: Factory,
) -> None:
    org, (emp,), casual = await setup_org(pg_session_factory, "Emp")
    await set_type(pg_session_factory, casual, carry_forward_days=D(5),
                created_at=datetime(NEW, 1, 2, tzinfo=UTC))  # fmt: skip
    assert await run(pg_session_factory, org, date(NEW, 1, 3)) == 0
    assert await carried(pg_session_factory, emp) == []


async def test_carries_on_the_policy_they_are_on_now(pg_session_factory: Factory) -> None:
    org, (moved, stayed, left, joined), casual = await setup_org(
        pg_session_factory, "Moved", "Stayed", "Left", "Joined"
    )
    await set_type(pg_session_factory, casual, carry_forward_days=D(5))
    async with pg_session_factory() as db:
        uk = LeavePolicy(org_id=org, name="UK", timezone="Europe/London")
        db.add(uk)
        await db.commit()
        uk_id = uk.id
    uk_type = await add_type(
        pg_session_factory, uk_id, "CL", annual_quota_days=D(12), carry_forward_days=D(3)
    )
    async with pg_session_factory() as db:
        profiles = EmployeeProfileRepository(db, org_id=org)
        mover = await profiles.get_by_user(moved)
        assert mover is not None
        mover.leave_policy_id, mover.leave_policy_assigned_on = uk_id, date(OLD, 1, 1)
        leaver = await profiles.get_by_user(left)
        assert leaver is not None
        leaver.status = EmployeeStatus.EXITED
        joiner = await profiles.get_by_user(joined)
        assert joiner is not None
        joiner.date_of_joining = date(NEW, 1, 1)
        await db.commit()

    assert await run(pg_session_factory, org, date(NEW, 1, 1)) == 2
    # Onto the new policy's type, from what's unused on it; nothing on the old one.
    assert await carried(pg_session_factory, moved) == [(uk_type, NEW, D(3))]
    assert await carried(pg_session_factory, stayed) == [(casual, NEW, D(5))]
    assert await carried(pg_session_factory, left) == []
    assert await carried(pg_session_factory, joined) == []


async def test_carried_days_pay_for_new_year_loss_of_pay(pg_session_factory: Factory) -> None:
    org, (emp,), casual = await setup_org(pg_session_factory, "Emp")
    await set_type(pg_session_factory, casual, annual_quota_days=D(2), carry_forward_days=D(2))
    # This year's 2 days are gone and 1 more day went to loss of pay.
    jan = date(NEW, 1, 5)
    await add_request(pg_session_factory, org, emp, jan, jan, "3", type_id=casual, lop="1")
    assert await run(pg_session_factory, org, date(NEW, 1, 6)) == 1
    async with pg_session_factory() as db:
        request = (
            await db.execute(select(LeaveRequest).where(LeaveRequest.user_id == emp))
        ).scalar_one()
        assert request.lop_days == D(0)
