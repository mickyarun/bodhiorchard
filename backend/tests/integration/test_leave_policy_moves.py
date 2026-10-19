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

"""Moving people between policies, holiday imports and recounts."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.models.leave_policy import LeavePolicy
from app.models.leave_request import ApprovalMode, LeaveKind, LeaveRequest, LeaveStatus
from app.models.policy_holiday import HolidayKind, HolidaySource, PolicyHoliday
from app.repositories.employee_profile import EmployeeProfileRepository
from app.repositories.leave_policy_members import LeavePolicyMemberRepository
from app.repositories.policy_holiday import PolicyHolidayRepository
from app.schemas.leave import LeaveRequestCreate
from app.services.leave import policy_admin
from app.services.leave.holidays import (
    HolidayImportError,
    import_public_holidays,
    recount_requests,
)
from app.services.leave.lifecycle import submit
from app.services.leave.policies import resolve_member_policy, today_for
from tests.integration.leave_support import (
    Factory,
    future_monday,
    leave_body,
    report_to,
    setup_org,
)

pytestmark = pytest.mark.integration


async def _policy(factory: Factory, org: uuid.UUID, name: str, **fields: object) -> LeavePolicy:
    async with factory() as db:
        policy = LeavePolicy(org_id=org, name=name, timezone="Asia/Kolkata", **fields)
        db.add(policy)
        await db.commit()
        return policy


async def _assigned_on(factory: Factory, org: uuid.UUID, user: uuid.UUID) -> date | None:
    async with factory() as db:
        profile = await EmployeeProfileRepository(db, org_id=org).get_by_user(user)
        assert profile is not None
        return profile.leave_policy_assigned_on


async def test_first_policy_keeps_joining_date_but_a_transfer_is_prorated(
    pg_session_factory: Factory,
) -> None:
    org, (emp, mgr), casual = await setup_org(pg_session_factory, "Emp", "Mgr")
    await report_to(pg_session_factory, org, emp, mgr)
    india = await _policy(pg_session_factory, org, "India")
    uk = await _policy(pg_session_factory, org, "UK")
    move_day = date(date.today().year, 10, 1)
    async with pg_session_factory() as db:
        members = LeavePolicyMemberRepository(db, org_id=org)
        # No leave history anywhere: setting up their first real policy
        # mustn't prorate them from today.
        assert await members.assign_employees(india, [emp], move_day) == 1
        await db.commit()
    assert await _assigned_on(pg_session_factory, org, emp) is None

    async with pg_session_factory() as db:
        # Back on the default policy, they request leave there…
        await LeavePolicyMemberRepository(db, org_id=org).assign_employees(
            (await resolve_member_policy(db, org, mgr)).policy, [emp], move_day
        )
        mon = future_monday()
        await submit(db, org, emp, leave_body(casual, mon, mon))
        # …so a later move is a real transfer, counted from the move.
        assert await LeavePolicyMemberRepository(db, org_id=org).assign_employees(
            uk, [emp], move_day
        )
        await db.commit()
    assert await _assigned_on(pg_session_factory, org, emp) == move_day


async def test_holiday_import_follows_the_leave_year_and_is_idempotent(
    pg_session_factory: Factory,
) -> None:
    org, _, _ = await setup_org(pg_session_factory, "Emp")
    april = await _policy(
        pg_session_factory,
        org,
        "Chennai",
        country_code="IN",
        subdivision_code="TN",
        year_start_month=4,
    )
    async with pg_session_factory() as db:
        added, skipped = await import_public_holidays(db, april, 2026)
        await db.commit()
        rows = await PolicyHolidayRepository(db, org_id=org).list_between(
            april.id, date(2000, 1, 1), date(2100, 1, 1)
        )
        assert added > 0 and skipped == 0
        assert all(date(2026, 4, 1) <= row.date <= date(2027, 3, 31) for row in rows)
        assert await import_public_holidays(db, april, 2026) == (0, added)
        nowhere = await _policy(pg_session_factory, org, "Remote")
        with pytest.raises(HolidayImportError):
            await import_public_holidays(db, nowhere, 2026)


async def test_recount_reprices_open_requests_but_not_leave_under_way(
    pg_session_factory: Factory,
) -> None:
    org, (emp, mgr), casual = await setup_org(pg_session_factory, "Emp", "Mgr")
    await report_to(pg_session_factory, org, emp, mgr)
    mon = future_monday()
    async with pg_session_factory() as db:
        policy = (await resolve_member_policy(db, org, emp)).policy
        today = today_for(policy)
        started = LeaveRequest(
            org_id=org,
            user_id=emp,
            policy_id=policy.id,
            kind=LeaveKind.LEAVE,
            leave_type_id=casual,
            start_date=today - timedelta(days=1),
            end_date=today + timedelta(days=1),
            days=Decimal("3"),
            status=LeaveStatus.APPROVED,
            approval_mode=ApprovalMode.MANUAL,
        )
        db.add(started)
        pending, _ = await submit(db, org, emp, leave_body(casual, mon, mon + timedelta(1)))
        for day in (today, mon):
            db.add(
                PolicyHoliday(
                    org_id=org,
                    policy_id=policy.id,
                    date=day,
                    name="Founders' day",
                    kind=HolidayKind.MANDATORY,
                    source=HolidaySource.MANUAL,
                )
            )
        await db.flush()
        assert await recount_requests(db, policy, today - timedelta(days=7)) == 1
        assert pending.days == Decimal("1")
        assert started.days == Decimal("3")


async def test_wfh_alone_is_not_policy_history(pg_session_factory: Factory) -> None:
    org, (emp, mgr), _ = await setup_org(pg_session_factory, "Emp", "Mgr")
    await report_to(pg_session_factory, org, emp, mgr)
    india = await _policy(pg_session_factory, org, "India")
    mon = future_monday()
    async with pg_session_factory() as db:
        await submit(
            db,
            org,
            emp,
            LeaveRequestCreate(kind=LeaveKind.WFH, start_date=mon, end_date=mon),
        )
        await LeavePolicyMemberRepository(db, org_id=org).assign_employees(
            india, [emp], date(date.today().year, 10, 1)
        )
        await db.commit()
    assert await _assigned_on(pg_session_factory, org, emp) is None


async def test_moving_someone_reports_requests_pending_on_their_old_policy(
    pg_session_factory: Factory,
) -> None:
    org, (emp, mgr, hr), casual = await setup_org(pg_session_factory, "Emp", "Mgr", "Hr")
    await report_to(pg_session_factory, org, emp, mgr)
    india = await _policy(pg_session_factory, org, "India")
    mon = future_monday()
    async with pg_session_factory() as db:
        await submit(db, org, emp, leave_body(casual, mon, mon))
        result = await policy_admin.assign_employees(
            db, india, hr, [emp, mgr], actor_is_owner=False
        )
        await db.commit()
    assert (result.assigned, result.pending_elsewhere) == (2, 1)
