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

"""Days past the balance become loss of pay instead of being refused."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest

from app.models.leave_ledger import LeaveLedgerEntry, LedgerEntryType
from app.models.leave_request import LeaveStatus
from app.models.policy_holiday import PolicyHoliday
from app.repositories.policy_holiday import PolicyHolidayRepository
from app.services.leave import cancellation
from app.services.leave.cancellation import cancel
from app.services.leave.evaluation import evaluate
from app.services.leave.holidays import recount_requests
from app.services.leave.lifecycle import decide, submit
from app.services.leave.policies import resolve_member_policy
from app.services.leave.summary import build_summary
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


async def test_days_past_the_balance_are_loss_of_pay(pg_session_factory: Factory) -> None:
    org, (emp, mgr), casual = await setup_org(pg_session_factory, "Emp", "Mgr")
    await report_to(pg_session_factory, org, emp, mgr)
    mon = future_monday()
    async with pg_session_factory() as db:
        # Mon to next Tue: 7 working days against a balance of 5.
        member = await resolve_member_policy(db, org, emp)
        body = leave_body(casual, mon, mon + timedelta(days=8))
        preview = await evaluate(db, member=member, user_id=emp, body=body)
        assert preview.problems == []
        assert (preview.days, preview.lop_days, preview.balance_after) == (D(7), D(2), D(0))
        first, _ = await submit(db, org, emp, body)
        # With nothing left, every day of the next one is loss of pay.
        later = mon + timedelta(days=14)
        second, _ = await submit(db, org, emp, leave_body(casual, later, later))
        await db.commit()
        assert (first.lop_days, second.lop_days) == (D(2), D(1))
        summary = await build_summary(db, org, emp, None)
        assert summary.balances[0].available == D(0) and summary.lop_days == D(3)


async def test_approval_prices_against_the_balance_at_that_moment(
    pg_session_factory: Factory,
) -> None:
    org, (emp, mgr), casual = await setup_org(pg_session_factory, "Emp", "Mgr")
    await report_to(pg_session_factory, org, emp, mgr)
    mon = future_monday()
    async with pg_session_factory() as db:
        request, _ = await submit(db, org, emp, leave_body(casual, mon, mon + timedelta(days=8)))
        await db.commit()
        assert request.lop_days == D(2)
        # HR tops the balance up before it's approved: no loss of pay any more.
        db.add(
            LeaveLedgerEntry(
                org_id=org,
                user_id=emp,
                leave_type_id=casual,
                leave_year=mon.year,
                entry_type=LedgerEntryType.ADJUSTMENT,
                days=D(2),
            )
        )
        await db.commit()
        approved = await decide(
            db, org_id=org, actor=mgr, perms=NOBODY, request_id=request.id, approve=True, note=None
        )
        await db.commit()
        assert approved.status == LeaveStatus.APPROVED and approved.lop_days == D(0)


async def test_fewer_days_give_back_loss_of_pay_first(pg_session_factory: Factory) -> None:
    org, (emp, mgr), casual = await setup_org(pg_session_factory, "Emp", "Mgr")
    await report_to(pg_session_factory, org, emp, mgr)
    mon = future_monday()
    async with pg_session_factory() as db:
        request, _ = await submit(db, org, emp, leave_body(casual, mon, mon + timedelta(days=8)))
        await db.commit()
        policy = (await resolve_member_policy(db, org, emp)).policy
        await PolicyHolidayRepository(db, org_id=org).create(
            PolicyHoliday(
                org_id=org, policy_id=policy.id, date=mon + timedelta(days=1), name="Diwali"
            )
        )
        assert await recount_requests(db, policy, mon) == 1
        await db.commit()
        await db.refresh(request)
        assert (request.days, request.lop_days) == (D(6), D(1))


async def test_cancelling_the_rest_gives_back_loss_of_pay_first(
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
        assert request.lop_days == D(2)
    # Back on Wednesday: Mon and Tue were taken, both covered by the balance.
    monkeypatch.setattr(cancellation, "today_for", lambda _policy: mon + timedelta(days=2))
    async with pg_session_factory() as db:
        cut = await cancel(db, org, emp, request.id)
        await db.commit()
    assert (cut.days, cut.lop_days) == (D(2), D(0))
