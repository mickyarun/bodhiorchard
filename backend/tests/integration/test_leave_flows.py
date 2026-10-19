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

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.deps import PermissionSet
from app.models.employee_profile import EmployeeProfile
from app.models.leave_policy import WfhApproval
from app.models.leave_request import LeaveKind, LeaveStatus
from app.models.leave_type import LeaveType
from app.models.organization import Organization
from app.models.policy_holiday import HolidayKind, PolicyHoliday
from app.models.user import OrgToUser, User
from app.repositories.employee_profile import EmployeeProfileRepository
from app.repositories.employee_reporting_manager import EmployeeReportingManagerRepository
from app.repositories.leave_type import LeaveTypeRepository
from app.repositories.policy_holiday import PolicyHolidayRepository
from app.schemas.leave import LeaveRequestCreate
from app.services.leave.calendar_view import calendar_view
from app.services.leave.evaluation import evaluate
from app.services.leave.holidays import recount_requests
from app.services.leave.lifecycle import cancel, decide, submit
from app.services.leave.policies import ensure_default_policy, resolve_member_policy, today_for
from app.services.leave.summary import build_summary

pytestmark = pytest.mark.integration

Factory = async_sessionmaker[AsyncSession]
NOBODY = PermissionSet(ids=frozenset(), is_owner=False)
HR = PermissionSet(ids=frozenset({"leave:approve"}), is_owner=False)


def _future_monday(weeks: int = 2) -> date:
    today = date.today()
    return today + timedelta(days=(7 - today.weekday()) % 7 + 7 * weeks)


def _month_mondays(months_ahead: int = 2) -> list[date]:
    first = (date.today().replace(day=1) + timedelta(days=32 * months_ahead)).replace(day=1)
    day = first + timedelta(days=(7 - first.weekday()) % 7)
    return [day + timedelta(weeks=n) for n in range(3)]


async def _setup(factory: Factory, *names: str) -> tuple[uuid.UUID, list[uuid.UUID], uuid.UUID]:
    """Org with members (each with a profile), a default policy and a 5-day type."""
    async with factory() as db:
        org = Organization(name=f"Leave {uuid.uuid4()}", slug=f"leave-{uuid.uuid4().hex[:8]}")
        db.add(org)
        await db.flush()
        ids = []
        for name in names:
            user = User(
                email=f"{name}-{uuid.uuid4().hex[:6]}@acme.dev", name=name, password_hash="x"
            )
            db.add(user)
            await db.flush()
            db.add(OrgToUser(user_id=user.id, org_id=org.id))
            db.add(EmployeeProfile(org_id=org.id, user_id=user.id))
            ids.append(user.id)
        policy = await ensure_default_policy(db, org.id)
        leave_type = await LeaveTypeRepository(db, org_id=org.id).create(
            LeaveType(
                org_id=org.id,
                policy_id=policy.id,
                name="Casual",
                code="CL",
                annual_quota_days=Decimal("5"),
            )
        )
        await db.commit()
        return org.id, ids, leave_type.id


async def _report_to(
    factory: Factory, org: uuid.UUID, employee: uuid.UUID, *managers: uuid.UUID
) -> None:
    async with factory() as db:
        profile = await EmployeeProfileRepository(db, org_id=org).get_by_user(employee)
        assert profile is not None
        await EmployeeReportingManagerRepository(db, org_id=org).replace_for_profile(
            profile.id, [(m, i == 0) for i, m in enumerate(managers)]
        )
        await db.commit()


def _leave(type_id: uuid.UUID, start: date, end: date, **kw: object) -> LeaveRequestCreate:
    return LeaveRequestCreate(
        kind=LeaveKind.LEAVE, leave_type_id=type_id, start_date=start, end_date=end, **kw
    )  # type: ignore[arg-type]


async def test_pending_counts_against_balance_and_first_decision_wins(
    pg_session_factory: Factory,
) -> None:
    org, (emp, m1, m2), casual = await _setup(pg_session_factory, "Emp", "M1", "M2")
    await _report_to(pg_session_factory, org, emp, m1, m2)
    mon = _future_monday()
    async with pg_session_factory() as db:
        request, _ = await submit(db, org, emp, _leave(casual, mon, mon + timedelta(days=2)))
        await db.commit()
        assert request.status == LeaveStatus.PENDING and request.days == Decimal("3")
        summary = await build_summary(db, org, emp, None)
        assert summary.balances[0].available == Decimal("2")
        assert {p.user_id for p in summary.approvers} == {m1, m2}
        await decide(
            db, org_id=org, actor=m2, perms=NOBODY, request_id=request.id, approve=True, note=None
        )
        await db.commit()
        with pytest.raises(HTTPException) as excinfo:
            await decide(
                db,
                org_id=org,
                actor=m1,
                perms=NOBODY,
                request_id=request.id,
                approve=False,
                note="x",
            )
        assert excinfo.value.status_code == 409


async def test_insufficient_balance_and_overlap_are_refused(pg_session_factory: Factory) -> None:
    org, (emp,), casual = await _setup(pg_session_factory, "Emp")
    mon = _future_monday()
    async with pg_session_factory() as db:
        member = await resolve_member_policy(db, org, emp)
        too_long = await evaluate(
            db, member=member, user_id=emp, body=_leave(casual, mon, mon + timedelta(days=7))
        )
        assert [p.code for p in too_long.problems] == ["insufficient_balance"]
        await submit(db, org, emp, _leave(casual, mon, mon))
        await db.commit()
        with pytest.raises(HTTPException, match="409"):
            await submit(
                db, org, emp, LeaveRequestCreate(kind=LeaveKind.WFH, start_date=mon, end_date=mon)
            )


async def test_nobody_decides_their_own_and_rejection_needs_a_note(
    pg_session_factory: Factory,
) -> None:
    org, (emp, mgr), casual = await _setup(pg_session_factory, "Emp", "Mgr")
    await _report_to(pg_session_factory, org, emp, mgr)
    mon = _future_monday()
    async with pg_session_factory() as db:
        request, _ = await submit(db, org, emp, _leave(casual, mon, mon))
        await db.commit()
        with pytest.raises(HTTPException) as own:
            await decide(
                db, org_id=org, actor=emp, perms=HR, request_id=request.id, approve=True, note=None
            )
        assert own.value.status_code == 403
        with pytest.raises(HTTPException) as no_note:
            await decide(
                db,
                org_id=org,
                actor=mgr,
                perms=NOBODY,
                request_id=request.id,
                approve=False,
                note=" ",
            )
        assert no_note.value.status_code == 422


async def test_without_a_manager_hr_decides_and_peers_cannot(pg_session_factory: Factory) -> None:
    org, (emp, hr, peer), casual = await _setup(pg_session_factory, "Emp", "Hr", "Peer")
    mon = _future_monday()
    async with pg_session_factory() as db:
        request, result = await submit(db, org, emp, _leave(casual, mon, mon))
        await db.commit()
        assert result.approvers.routes_to_hr
        with pytest.raises(HTTPException) as peer_try:
            await decide(
                db,
                org_id=org,
                actor=peer,
                perms=NOBODY,
                request_id=request.id,
                approve=True,
                note=None,
            )
        assert peer_try.value.status_code == 403
        decided = await decide(
            db, org_id=org, actor=hr, perms=HR, request_id=request.id, approve=True, note=None
        )
        assert decided.status == LeaveStatus.APPROVED


async def test_wfh_auto_approved_within_monthly_allowance(pg_session_factory: Factory) -> None:
    org, (emp,), _ = await _setup(pg_session_factory, "Emp")
    async with pg_session_factory() as db:
        policy = (await resolve_member_policy(db, org, emp)).policy
        policy.wfh_approval = WfhApproval.AUTO_WITHIN_ALLOWANCE
        policy.wfh_monthly_auto_days = 2
        await db.commit()
        week1, week2, _ = _month_mondays()
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
    org, (emp,), _ = await _setup(pg_session_factory, "Emp")
    monday = _month_mondays()[0]
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
        with pytest.raises(HTTPException, match="optional holidays"):
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
    org, (emp,), casual = await _setup(pg_session_factory, "Emp")
    mon = _future_monday()
    async with pg_session_factory() as db:
        request, _ = await submit(db, org, emp, _leave(casual, mon, mon + timedelta(days=4)))
        await db.commit()
        cancelled = await cancel(db, org, emp, request.id)
        await db.commit()
        assert cancelled.status == LeaveStatus.CANCELLED
        assert (await build_summary(db, org, emp, None)).balances[0].available == Decimal("5")


async def test_calendar_hides_leave_type_from_peers(pg_session_factory: Factory) -> None:
    org, (emp, mgr, peer), casual = await _setup(pg_session_factory, "Emp", "Mgr", "Peer")
    await _report_to(pg_session_factory, org, emp, mgr)
    mon = _future_monday()
    async with pg_session_factory() as db:
        request, _ = await submit(db, org, emp, _leave(casual, mon, mon, reason="Fever"))
        await decide(
            db, org_id=org, actor=mgr, perms=NOBODY, request_id=request.id, approve=True, note=None
        )
        await db.commit()
        as_peer = await calendar_view(db, org, peer, NOBODY, mon, mon)
        as_mgr = await calendar_view(db, org, mgr, NOBODY, mon, mon)
        assert as_peer.entries[0].leave_type is None and as_peer.entries[0].reason is None
        assert as_mgr.entries[0].leave_type is not None and as_mgr.entries[0].reason == "Fever"


async def test_new_holiday_recounts_pending_days(pg_session_factory: Factory) -> None:
    org, (emp,), casual = await _setup(pg_session_factory, "Emp")
    mon = _future_monday()
    async with pg_session_factory() as db:
        request, _ = await submit(db, org, emp, _leave(casual, mon, mon + timedelta(days=2)))
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
