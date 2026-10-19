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

"""Loss of pay as requests and balances change after the request was made."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest

from app.models.leave_type import LeaveType
from app.models.policy_holiday import PolicyHoliday
from app.repositories.policy_holiday import PolicyHolidayRepository
from app.services.leave import adjustments, cancellation
from app.services.leave.cancellation import cancel
from app.services.leave.holidays import recount_requests
from app.services.leave.lifecycle import decide, submit
from app.services.leave.policies import resolve_member_policy
from tests.integration.leave_support import (
    NOBODY,
    Factory,
    future_monday,
    leave_body,
    report_to,
    setup_org,
)

pytestmark = pytest.mark.integration
D = Decimal


async def test_cancelling_most_of_a_leave_with_loss_of_pay(
    pg_session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    org, (emp, mgr), casual = await setup_org(pg_session_factory, "Emp", "Mgr")
    await report_to(pg_session_factory, org, emp, mgr)
    mon = future_monday()
    async with pg_session_factory() as db:
        request, _ = await submit(db, org, emp, leave_body(casual, mon, mon + timedelta(days=8)))
        await decide(
            db, org_id=org, actor=mgr, perms=NOBODY, request_id=request.id, approve=True, note=None
        )
        await db.commit()
    # Back on Tuesday: one day taken, fewer than the 2 days of loss of pay.
    monkeypatch.setattr(cancellation, "today_for", lambda _policy: mon + timedelta(days=1))
    async with pg_session_factory() as db:
        cut = await cancel(db, org, emp, request.id)
        await db.commit()
    assert (cut.days, cut.lop_days) == (D(1), D(0))


async def test_a_holiday_on_an_unpaid_day_is_saved(pg_session_factory: Factory) -> None:
    org, (emp, mgr), casual = await setup_org(pg_session_factory, "Emp", "Mgr")
    await report_to(pg_session_factory, org, emp, mgr)
    mon = future_monday()
    later = mon + timedelta(days=14)
    async with pg_session_factory() as db:
        await submit(db, org, emp, leave_body(casual, mon, mon + timedelta(days=4)))
        unpaid, _ = await submit(db, org, emp, leave_body(casual, later, later))
        await db.commit()
        assert unpaid.lop_days == D(1)
        policy = (await resolve_member_policy(db, org, emp)).policy
        await PolicyHolidayRepository(db, org_id=org).create(
            PolicyHoliday(org_id=org, policy_id=policy.id, date=later, name="Pongal")
        )
        assert await recount_requests(db, policy, mon) == 1
        await db.commit()
        await db.refresh(unpaid)
        assert (unpaid.days, unpaid.lop_days) == (D(0), D(0))


async def test_freed_balance_goes_back_to_loss_of_pay(pg_session_factory: Factory) -> None:
    org, (emp, mgr), casual = await setup_org(pg_session_factory, "Emp", "Mgr")
    await report_to(pg_session_factory, org, emp, mgr)
    mon = future_monday()
    later = mon + timedelta(days=14)
    async with pg_session_factory() as db:
        paid, _ = await submit(db, org, emp, leave_body(casual, mon, mon + timedelta(days=4)))
        unpaid, _ = await submit(db, org, emp, leave_body(casual, later, later + timedelta(1)))
        await db.commit()
        assert (paid.lop_days, unpaid.lop_days) == (D(0), D(2))
        # Rejecting the first request frees its 5 days for the second.
        await decide(
            db, org_id=org, actor=mgr, perms=NOBODY, request_id=paid.id, approve=False, note="No"
        )
        await db.commit()
        await db.refresh(unpaid)
        assert unpaid.lop_days == D(0)


async def test_hr_top_up_covers_earlier_loss_of_pay(pg_session_factory: Factory) -> None:
    org, (emp, mgr), casual = await setup_org(pg_session_factory, "Emp", "Mgr")
    await report_to(pg_session_factory, org, emp, mgr)
    mon = future_monday()
    async with pg_session_factory() as db:
        request, _ = await submit(db, org, emp, leave_body(casual, mon, mon + timedelta(days=8)))
        await db.commit()
        change = adjustments.BalanceChange(
            org_id=org,
            actor_id=mgr,
            actor_is_owner=False,
            user_id=emp,
            leave_type_id=casual,
            leave_year=None,
        )
        await adjustments.adjust(db, change, D(1), "Carry forward")
        await db.commit()
        await db.refresh(request)
        assert request.lop_days == D(1)


async def test_switching_a_type_off_keeps_its_loss_of_pay(pg_session_factory: Factory) -> None:
    org, (emp, mgr), casual = await setup_org(pg_session_factory, "Emp", "Mgr")
    await report_to(pg_session_factory, org, emp, mgr)
    mon = future_monday()
    async with pg_session_factory() as db:
        request, _ = await submit(db, org, emp, leave_body(casual, mon, mon + timedelta(days=8)))
        leave_type = await db.get(LeaveType, casual)
        assert leave_type is not None
        leave_type.is_active = False
        await db.commit()
        approved = await decide(
            db, org_id=org, actor=mgr, perms=NOBODY, request_id=request.id, approve=True, note=None
        )
        await db.commit()
        assert approved.lop_days == D(2)
