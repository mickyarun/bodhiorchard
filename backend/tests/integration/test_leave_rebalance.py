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

"""A balance that shrinks under booked leave turns the uncovered days into loss of pay.

Days left never go below zero: the paid and loss-of-pay split of booked
leave, the Leave page, the request preview and the approver's card all
read the same balance.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.models.leave_request import LeaveRequest
from app.models.leave_type import LeaveAccrual, LeaveType
from app.services.leave import adjustments
from app.services.leave.balance_after import balances_after
from app.services.leave.evaluation import evaluate
from app.services.leave.lifecycle import submit
from app.services.leave.policies import resolve_member_policy
from app.services.leave.summary import build_summary
from tests.integration.leave_support import Factory, leave_body, report_to, setup_org

pytestmark = pytest.mark.integration
D = Decimal
# Next year, so every month is still ahead: 12 a year monthly is 1 a month.
YEAR = date.today().year + 1


def _first_monday(month: int) -> date:
    first = date(YEAR, month, 1)
    return first + timedelta(days=(7 - first.weekday()) % 7)


async def _set_type(factory: Factory, type_id: uuid.UUID, accrual: LeaveAccrual) -> None:
    async with factory() as db:
        leave_type = await db.get(LeaveType, type_id)
        assert leave_type is not None
        leave_type.annual_quota_days, leave_type.accrual = D(12), accrual
        await db.commit()


def _change(
    org: uuid.UUID, hr: uuid.UUID, emp: uuid.UUID, type_id: uuid.UUID
) -> adjustments.BalanceChange:
    return adjustments.BalanceChange(
        org_id=org,
        actor_id=hr,
        actor_is_owner=False,
        user_id=emp,
        leave_type_id=type_id,
        leave_year=YEAR,
        sees_restricted=False,
    )


async def _left(factory: Factory, org: uuid.UUID, emp: uuid.UUID) -> tuple[Decimal, Decimal]:
    """The Leave page's days left and loss of pay for the year."""
    async with factory() as db:
        summary = await build_summary(db, org, emp, YEAR)
    available = summary.balances[0].available
    assert available is not None
    return available, summary.lop_days


async def test_removed_days_turn_booked_leave_into_loss_of_pay(
    pg_session_factory: Factory,
) -> None:
    org, (emp, mgr, hr), casual = await setup_org(pg_session_factory, "Emp", "Mgr", "Hr")
    await report_to(pg_session_factory, org, emp, mgr)
    await _set_type(pg_session_factory, casual, LeaveAccrual.MONTHLY)
    nov = _first_monday(11)
    async with pg_session_factory() as db:
        # Two working weeks in November: 11 earned by then, all 10 paid.
        request, _ = await submit(db, org, emp, leave_body(casual, nov, nov + timedelta(days=11)))
        await db.commit()
        assert (request.days, request.lop_days) == (D(10), D(0))
    async with pg_session_factory() as db:
        # HR takes 3 days off the year: 9 in all now, one short of what's booked.
        await adjustments.adjust(db, _change(org, hr, emp, casual), D(-3), "Correction")
        await db.commit()
        repriced = await db.get(LeaveRequest, request.id)
        assert repriced is not None and repriced.lop_days == D(1)
    assert await _left(pg_session_factory, org, emp) == (D(0), D(1))
    async with pg_session_factory() as db:
        # Nothing left in December either: the preview and the type picker agree.
        member = await resolve_member_policy(db, org, emp)
        dec = _first_monday(12)
        preview = await evaluate(
            db, member=member, user_id=emp, body=leave_body(casual, dec, dec + timedelta(days=1))
        )
        assert (preview.balance_before, preview.lop_days) == (D(0), D(2))
        assert preview.balances_on_start == {casual: D(0)}
        # The approver's card for the November leave: nothing left, not overdrawn.
        pending = await db.get(LeaveRequest, request.id)
        assert pending is not None
        assert (await balances_after(db, org, [pending]))[pending.id].days == D(0)


async def test_days_taken_away_leave_early_leave_paid(pg_session_factory: Factory) -> None:
    """A deduction comes off the year's total, not January's day."""
    org, (emp, mgr, hr), casual = await setup_org(pg_session_factory, "Emp", "Mgr", "Hr")
    await report_to(pg_session_factory, org, emp, mgr)
    await _set_type(pg_session_factory, casual, LeaveAccrual.MONTHLY)
    jan = _first_monday(1)
    async with pg_session_factory() as db:
        request, _ = await submit(db, org, emp, leave_body(casual, jan, jan))
        await db.commit()
        assert request.lop_days == D(0)
    async with pg_session_factory() as db:
        await adjustments.adjust(db, _change(org, hr, emp, casual), D(-2), "Correction")
        await db.commit()
        kept = await db.get(LeaveRequest, request.id)
        assert kept is not None and kept.lop_days == D(0)
    assert await _left(pg_session_factory, org, emp) == (D(0), D(0))


async def test_a_grant_still_pays_early_leave_after_a_later_deduction(
    pg_session_factory: Factory,
) -> None:
    """Added days count from the start; days taken away aren't netted against them."""
    org, (emp, mgr, hr), casual = await setup_org(pg_session_factory, "Emp", "Mgr", "Hr")
    await report_to(pg_session_factory, org, emp, mgr)
    await _set_type(pg_session_factory, casual, LeaveAccrual.MONTHLY)
    change = _change(org, hr, emp, casual)
    apr = _first_monday(4)
    async with pg_session_factory() as db:
        await adjustments.adjust(db, change, D(5), "Joining bonus")
        # Mon to the next Tue in April: 7 days against 4 earned + 5 added.
        request, _ = await submit(db, org, emp, leave_body(casual, apr, apr + timedelta(days=8)))
        await db.commit()
        assert (request.days, request.lop_days) == (D(7), D(0))
    async with pg_session_factory() as db:
        # The year still holds 12 days, more than the 7 booked.
        await adjustments.adjust(db, change, D(-5), "Bonus withdrawn")
        await db.commit()
        kept = await db.get(LeaveRequest, request.id)
        assert kept is not None and kept.lop_days == D(0)
    assert (await _left(pg_session_factory, org, emp))[1] == D(0)


async def test_recalculating_reprices_leave_priced_under_an_earlier_rule(
    pg_session_factory: Factory,
) -> None:
    org, (emp, mgr, hr), casual = await setup_org(pg_session_factory, "Emp", "Mgr", "Hr")
    await report_to(pg_session_factory, org, emp, mgr)
    await _set_type(pg_session_factory, casual, LeaveAccrual.UPFRONT)
    nov = _first_monday(11)
    async with pg_session_factory() as db:
        # Four working weeks while the year's 12 days were given upfront.
        request, _ = await submit(db, org, emp, leave_body(casual, nov, nov + timedelta(days=25)))
        await db.commit()
        assert (request.days, request.lop_days) == (D(20), D(8))
    # Switched to monthly afterwards: only 11 are earned by November, so
    # one of its 12 paid days isn't covered. Days left still stop at zero.
    await _set_type(pg_session_factory, casual, LeaveAccrual.MONTHLY)
    assert await _left(pg_session_factory, org, emp) == (D(0), D(8))
    async with pg_session_factory() as db:
        result = await adjustments.recalculate(db, _change(org, hr, emp, casual))
        await db.commit()
        assert result.correction == D(0)
        repriced = await db.get(LeaveRequest, request.id)
        assert repriced is not None and repriced.lop_days == D(9)
    assert await _left(pg_session_factory, org, emp) == (D(0), D(9))
