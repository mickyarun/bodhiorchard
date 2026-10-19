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

"""Leave, WFH and optional holidays end to end against real Postgres."""

from __future__ import annotations

import asyncio
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.api.v1._leave_errors import status_for
from app.models.leave_policy import ProrationMethod, WfhApproval
from app.models.leave_request import LeaveKind, LeaveStatus
from app.models.organization import Organization
from app.models.policy_holiday import HolidayKind, PolicyHoliday
from app.repositories.employee_profile import EmployeeProfileRepository
from app.repositories.leave_ledger import LeaveLedgerRepository
from app.repositories.leave_policy_members import LeavePolicyMemberRepository
from app.repositories.policy_holiday import PolicyHolidayRepository
from app.repositories.user import UserRepository
from app.schemas.leave import LeaveRequestCreate
from app.services.leave.calendar_view import calendar_view
from app.services.leave.cancellation import cancel
from app.services.leave.errors import LeaveError
from app.services.leave.evaluation import evaluate
from app.services.leave.holidays import recount_requests
from app.services.leave.lifecycle import decide, submit
from app.services.leave.policies import ensure_default_policy, resolve_member_policy, today_for
from app.services.leave.summary import build_summary
from tests.integration.leave_support import (
    HR,
    NOBODY,
    Factory,
    future_monday,
    give_role,
    leave_body,
    month_mondays,
    report_to,
    setup_org,
)

pytestmark = pytest.mark.integration


async def test_pending_counts_against_balance_and_first_decision_wins(
    pg_session_factory: Factory,
) -> None:
    org, (emp, m1, m2), casual = await setup_org(pg_session_factory, "Emp", "M1", "M2")
    await report_to(pg_session_factory, org, emp, m1, m2)
    mon = future_monday()
    async with pg_session_factory() as db:
        request, _ = await submit(db, org, emp, leave_body(casual, mon, mon + timedelta(days=2)))
        await db.commit()
        assert request.status == LeaveStatus.PENDING and request.days == Decimal("3")
        summary = await build_summary(db, org, emp, None)
        assert summary.balances[0].available == Decimal("2")
        assert {p.user_id for p in summary.approvers} == {m1, m2}
        await decide(
            db, org_id=org, actor=m2, perms=NOBODY, request_id=request.id, approve=True, note=None
        )
        await db.commit()
        with pytest.raises(LeaveError) as excinfo:
            await decide(
                db,
                org_id=org,
                actor=m1,
                perms=NOBODY,
                request_id=request.id,
                approve=False,
                note="x",
            )
        assert status_for(excinfo.value) == 409
        assert str(excinfo.value) == "M2 already approved this request."


async def test_overlap_is_refused(pg_session_factory: Factory) -> None:
    org, (emp, mgr), casual = await setup_org(pg_session_factory, "Emp", "Mgr")
    await report_to(pg_session_factory, org, emp, mgr)
    mon = future_monday()
    async with pg_session_factory() as db:
        await submit(db, org, emp, leave_body(casual, mon, mon))
        await db.commit()
        with pytest.raises(LeaveError, match="already have a pending request"):
            await submit(
                db, org, emp, LeaveRequestCreate(kind=LeaveKind.WFH, start_date=mon, end_date=mon)
            )


async def test_nobody_decides_their_own_and_rejection_needs_a_note(
    pg_session_factory: Factory,
) -> None:
    org, (emp, mgr), casual = await setup_org(pg_session_factory, "Emp", "Mgr")
    await report_to(pg_session_factory, org, emp, mgr)
    mon = future_monday()
    async with pg_session_factory() as db:
        request, _ = await submit(db, org, emp, leave_body(casual, mon, mon))
        await db.commit()
        with pytest.raises(LeaveError) as own:
            await decide(
                db, org_id=org, actor=emp, perms=HR, request_id=request.id, approve=True, note=None
            )
        assert status_for(own.value) == 403
        with pytest.raises(LeaveError) as no_note:
            await decide(
                db,
                org_id=org,
                actor=mgr,
                perms=NOBODY,
                request_id=request.id,
                approve=False,
                note=" ",
            )
        assert status_for(no_note.value) == 422


async def test_without_a_manager_hr_decides_and_peers_cannot(pg_session_factory: Factory) -> None:
    org, (emp, hr, peer), casual = await setup_org(pg_session_factory, "Emp", "Hr", "Peer")
    await give_role(pg_session_factory, org, hr, "hr")
    mon = future_monday()
    async with pg_session_factory() as db:
        request, result = await submit(db, org, emp, leave_body(casual, mon, mon))
        await db.commit()
        assert result.approvers.routes_to_hr
        with pytest.raises(LeaveError) as peer_try:
            await decide(
                db,
                org_id=org,
                actor=peer,
                perms=NOBODY,
                request_id=request.id,
                approve=True,
                note=None,
            )
        assert status_for(peer_try.value) == 403
        decided = await decide(
            db, org_id=org, actor=hr, perms=HR, request_id=request.id, approve=True, note=None
        )
        assert decided.status == LeaveStatus.APPROVED


async def test_wfh_auto_approved_within_monthly_allowance(pg_session_factory: Factory) -> None:
    org, (emp, mgr), _ = await setup_org(pg_session_factory, "Emp", "Mgr")
    await report_to(pg_session_factory, org, emp, mgr)
    async with pg_session_factory() as db:
        policy = (await resolve_member_policy(db, org, emp)).policy
        policy.wfh_approval = WfhApproval.AUTO_WITHIN_ALLOWANCE
        policy.wfh_monthly_auto_days = 2
        await db.commit()
        week1, week2, _ = month_mondays()
        first, _ = await submit(
            db,
            org,
            emp,
            LeaveRequestCreate(
                kind=LeaveKind.WFH, start_date=week1, end_date=week1 + timedelta(days=1)
            ),
        )
        await db.commit()
        second, _ = await submit(
            db, org, emp, LeaveRequestCreate(kind=LeaveKind.WFH, start_date=week2, end_date=week2)
        )
        await db.commit()
        assert first.status == LeaveStatus.APPROVED
        assert second.status == LeaveStatus.PENDING


async def test_optional_holiday_quota(pg_session_factory: Factory) -> None:
    org, (emp, mgr), _ = await setup_org(pg_session_factory, "Emp", "Mgr")
    await report_to(pg_session_factory, org, emp, mgr)
    monday = month_mondays()[0]
    async with pg_session_factory() as db:
        policy = (await resolve_member_policy(db, org, emp)).policy
        policy.optional_holiday_quota = 1
        repo = PolicyHolidayRepository(db, org_id=org)
        h1 = await repo.create(
            PolicyHoliday(
                org_id=org,
                policy_id=policy.id,
                date=monday,
                name="Pongal",
                kind=HolidayKind.OPTIONAL,
            )
        )
        h2 = await repo.create(
            PolicyHoliday(
                org_id=org,
                policy_id=policy.id,
                date=monday + timedelta(days=1),
                name="Onam",
                kind=HolidayKind.OPTIONAL,
            )
        )
        await db.commit()
        taken, _ = await submit(
            db,
            org,
            emp,
            LeaveRequestCreate(
                kind=LeaveKind.OPTIONAL_HOLIDAY,
                holiday_id=h1.id,
                start_date=monday,
                end_date=monday,
            ),
        )
        await db.commit()
        assert taken.days == Decimal("1")
        with pytest.raises(LeaveError, match="optional holidays"):
            await submit(
                db,
                org,
                emp,
                LeaveRequestCreate(
                    kind=LeaveKind.OPTIONAL_HOLIDAY,
                    holiday_id=h2.id,
                    start_date=monday,
                    end_date=monday,
                ),
            )


async def test_cancel_pending_frees_the_balance(pg_session_factory: Factory) -> None:
    org, (emp, mgr), casual = await setup_org(pg_session_factory, "Emp", "Mgr")
    await report_to(pg_session_factory, org, emp, mgr)
    mon = future_monday()
    async with pg_session_factory() as db:
        request, _ = await submit(db, org, emp, leave_body(casual, mon, mon + timedelta(days=4)))
        await db.commit()
        cancelled = await cancel(db, org, emp, request.id)
        await db.commit()
        assert cancelled.status == LeaveStatus.CANCELLED
        assert (await build_summary(db, org, emp, None)).balances[0].available == Decimal("5")


async def test_calendar_hides_leave_type_from_peers(pg_session_factory: Factory) -> None:
    org, (emp, mgr, peer), casual = await setup_org(pg_session_factory, "Emp", "Mgr", "Peer")
    await report_to(pg_session_factory, org, emp, mgr)
    mon = future_monday()
    async with pg_session_factory() as db:
        request, _ = await submit(db, org, emp, leave_body(casual, mon, mon, reason="Fever"))
        await decide(
            db, org_id=org, actor=mgr, perms=NOBODY, request_id=request.id, approve=True, note=None
        )
        await db.commit()
        as_peer = await calendar_view(db, org, peer, NOBODY, mon, mon)
        as_mgr = await calendar_view(db, org, mgr, NOBODY, mon, mon)
        assert as_peer.entries[0].leave_type is None and as_peer.entries[0].reason is None
        assert as_mgr.entries[0].leave_type is not None and as_mgr.entries[0].reason == "Fever"


async def test_new_holiday_recounts_pending_days(pg_session_factory: Factory) -> None:
    org, (emp, mgr), casual = await setup_org(pg_session_factory, "Emp", "Mgr")
    await report_to(pg_session_factory, org, emp, mgr)
    mon = future_monday()
    async with pg_session_factory() as db:
        request, _ = await submit(db, org, emp, leave_body(casual, mon, mon + timedelta(days=2)))
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
        assert request.days == Decimal("2")
        assert today_for(policy) <= mon


async def test_default_policy_creation_survives_a_race(pg_session_factory: Factory) -> None:
    """The Leave page loads several endpoints at once on first visit."""
    async with pg_session_factory() as db:
        org = Organization(name=f"Race {uuid.uuid4()}", slug=f"race-{uuid.uuid4().hex[:8]}")
        db.add(org)
        await db.commit()

    async def first_visit() -> uuid.UUID:
        async with pg_session_factory() as db:
            policy = await ensure_default_policy(db, org.id)
            await db.commit()
            return policy.id

    ids = await asyncio.gather(*(first_visit() for _ in range(5)))
    assert len(set(ids)) == 1


async def test_reads_never_freeze_allocations_but_submit_does(pg_session_factory: Factory) -> None:
    org, (emp, mgr), casual = await setup_org(pg_session_factory, "Emp", "Mgr")
    await report_to(pg_session_factory, org, emp, mgr)
    async with pg_session_factory() as db:
        policy = (await resolve_member_policy(db, org, emp)).policy
        this_year = today_for(policy).year  # the default policy's year starts in January
        await build_summary(db, org, emp, None)
        await build_summary(db, org, emp, this_year + 1)
        await db.commit()
        ledger = LeaveLedgerRepository(db, org_id=org)
        assert await ledger.list_for(emp, this_year) == []
        assert await ledger.list_for(emp, this_year + 1) == []
        mon = future_monday()
        await submit(db, org, emp, leave_body(casual, mon, mon))
        await db.commit()
        entries = await LeaveLedgerRepository(db, org_id=org).list_for(emp, mon.year)
        assert [e.entry_type.value for e in entries] == ["allocation"]


async def test_manager_who_left_the_org_no_longer_approves(pg_session_factory: Factory) -> None:
    org, (emp, mgr, hr), casual = await setup_org(pg_session_factory, "Emp", "Mgr", "Hr")
    await report_to(pg_session_factory, org, emp, mgr)
    await give_role(pg_session_factory, org, hr, "hr")
    async with pg_session_factory() as db:
        user = await UserRepository(db).get_by_id(mgr)
        assert user is not None
        user.is_active = False
        await db.commit()
        summary = await build_summary(db, org, emp, None)
        assert summary.routes_to_hr and summary.approvers == []


async def test_assigning_the_default_policy_keeps_implicit_followers(
    pg_session_factory: Factory,
) -> None:
    org, (emp,), _ = await setup_org(pg_session_factory, "Emp")
    async with pg_session_factory() as db:
        policy = await ensure_default_policy(db, org)
        assigned = await LeavePolicyMemberRepository(db, org_id=org).assign_employees(
            policy, [emp], date.today()
        )
        assert assigned == 0


async def test_wfh_request_never_carries_a_leave_type(pg_session_factory: Factory) -> None:
    org, (emp, mgr), casual = await setup_org(pg_session_factory, "Emp", "Mgr")
    await report_to(pg_session_factory, org, emp, mgr)
    mon = future_monday()
    async with pg_session_factory() as db:
        request, _ = await submit(
            db,
            org,
            emp,
            LeaveRequestCreate(
                kind=LeaveKind.WFH, leave_type_id=casual, start_date=mon, end_date=mon
            ),
        )
        assert request.leave_type_id is None


async def test_request_with_nobody_to_approve_is_refused(pg_session_factory: Factory) -> None:
    org, (emp,), casual = await setup_org(pg_session_factory, "Emp")
    mon = future_monday()
    async with pg_session_factory() as db:
        member = await resolve_member_policy(db, org, emp)
        result = await evaluate(db, member=member, user_id=emp, body=leave_body(casual, mon, mon))
        assert [p.code for p in result.problems] == ["no_approver"]


async def test_request_beyond_next_leave_year_is_refused(pg_session_factory: Factory) -> None:
    org, (emp, mgr), casual = await setup_org(pg_session_factory, "Emp", "Mgr")
    await report_to(pg_session_factory, org, emp, mgr)
    far = date(date.today().year + 3, 3, 2)
    async with pg_session_factory() as db:
        member = await resolve_member_policy(db, org, emp)
        result = await evaluate(db, member=member, user_id=emp, body=leave_body(casual, far, far))
        assert [p.code for p in result.problems] == ["too_far_ahead"]


async def test_cancelling_an_approved_future_request(pg_session_factory: Factory) -> None:
    org, (emp, mgr), casual = await setup_org(pg_session_factory, "Emp", "Mgr")
    await report_to(pg_session_factory, org, emp, mgr)
    mon = future_monday()
    async with pg_session_factory() as db:
        request, _ = await submit(db, org, emp, leave_body(casual, mon, mon))
        await decide(
            db, org_id=org, actor=mgr, perms=NOBODY, request_id=request.id, approve=True, note=None
        )
        await db.commit()
        cancelled = await cancel(db, org, emp, request.id)
        assert cancelled.status == LeaveStatus.CANCELLED


async def test_mid_year_joiner_gets_a_prorated_allocation(pg_session_factory: Factory) -> None:
    org, (emp,), _ = await setup_org(pg_session_factory, "Emp")
    year = date.today().year
    async with pg_session_factory() as db:
        policy = (await resolve_member_policy(db, org, emp)).policy
        policy.proration_method = ProrationMethod.MONTHLY
        policy.proration_cutoff_day = 15
        profile = await EmployeeProfileRepository(db, org_id=org).get_by_user(emp)
        assert profile is not None
        profile.date_of_joining = date(year, 7, 20)
        await db.commit()
        summary = await build_summary(db, org, emp, year)
        # Aug to Dec: 5 x 5 / 12 = 2.08, to the nearest half day.
        assert [b.allocated for b in summary.balances] == [Decimal("2.0")]
