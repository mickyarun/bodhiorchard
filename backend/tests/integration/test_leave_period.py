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

"""Period leave: women only, approved at once, at most one day a month."""

from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient

from app.models.employee_profile import Gender
from app.models.leave_request import ApprovalMode, LeaveStatus
from app.models.leave_type import LeaveEligibility, LeaveType
from app.repositories.employee_profile import EmployeeProfileRepository
from app.services.leave.errors import LeaveConflictError
from app.services.leave.lifecycle import submit
from app.services.leave.policies import ensure_default_policy
from app.services.leave.summary import build_summary
from tests.integration.leave_support import (
    Factory,
    as_user,
    give_role,
    leave_body,
    month_mondays,
    report_to,
    setup_org,
)

pytestmark = pytest.mark.integration
LEAVE = "/api/v1/leave"


async def _period_leave(factory: Factory, org: uuid.UUID, woman: uuid.UUID) -> uuid.UUID:
    """Adds period leave to the default policy and marks ``woman`` as female."""
    async with factory() as db:
        policy = await ensure_default_policy(db, org)
        period = LeaveType(
            org_id=org, policy_id=policy.id, name="Period leave", code="PERIOD",
            annual_quota_days=Decimal("12"), eligibility=LeaveEligibility.WOMEN,
            auto_approve=True, monthly_limit_days=Decimal("1"), counts_toward_warning=False,
        )  # fmt: skip
        db.add(period)
        profile = await EmployeeProfileRepository(db, org_id=org).get_by_user(woman)
        assert profile is not None
        profile.gender = Gender.FEMALE
        await db.commit()
        return period.id


async def test_only_women_see_and_can_request_it(pg_session_factory: Factory) -> None:
    org, (woman, man), _casual = await setup_org(pg_session_factory, "Asha", "Ravi")
    period = await _period_leave(pg_session_factory, org, woman)
    mon = month_mondays()[0]
    async with pg_session_factory() as db:
        hers = await build_summary(db, org, woman, None)
        his = await build_summary(db, org, man, None)
        assert "Period leave" in {b.leave_type.name for b in hers.balances}
        assert "Period leave" not in {b.leave_type.name for b in his.balances}
        with pytest.raises(LeaveConflictError, match="isn't available to you"):
            await submit(db, org, man, leave_body(period, mon, mon))


async def test_approved_at_once_even_with_no_manager(pg_session_factory: Factory) -> None:
    org, (woman,), _casual = await setup_org(pg_session_factory, "Asha")
    period = await _period_leave(pg_session_factory, org, woman)
    mon = month_mondays()[0]
    async with pg_session_factory() as db:
        request, _ = await submit(db, org, woman, leave_body(period, mon, mon))
        await db.commit()
        assert request.status == LeaveStatus.APPROVED
        assert request.approval_mode == ApprovalMode.AUTO_POLICY
        assert request.decided_at is not None


async def test_one_day_a_month_and_unused_days_do_not_carry(
    pg_session_factory: Factory,
) -> None:
    org, (woman,), _casual = await setup_org(pg_session_factory, "Asha")
    period = await _period_leave(pg_session_factory, org, woman)
    first, second, _third = month_mondays()
    async with pg_session_factory() as db:
        # Two days at once is over the limit, even with nothing booked yet.
        with pytest.raises(LeaveConflictError, match="1 day a month"):
            await submit(db, org, woman, leave_body(period, first, first + timedelta(days=1)))
        await submit(db, org, woman, leave_body(period, first, first))
        await db.commit()
        with pytest.raises(LeaveConflictError, match="already have 1 day booked"):
            await submit(db, org, woman, leave_body(period, second, second))
        # A month with none used doesn't give two.
        next_month = month_mondays(3)
        await submit(db, org, woman, leave_body(period, next_month[0], next_month[0]))
        await db.commit()
        with pytest.raises(LeaveConflictError):
            await submit(db, org, woman, leave_body(period, next_month[1], next_month[1]))


async def test_hr_sets_it_up_over_the_api(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, (woman, hr), _casual = await setup_org(pg_session_factory, "Asha", "Hr")
    await give_role(pg_session_factory, org, hr, "hr")
    async with pg_session_factory() as db:
        policy = await ensure_default_policy(db, org)
        profile = await EmployeeProfileRepository(db, org_id=org).get_by_user(woman)
        assert profile is not None
        profile.gender = Gender.FEMALE
        await db.commit()
    body = {
        "name": "Period leave", "code": "PERIOD", "annual_quota_days": "12",
        "eligibility": "women", "auto_approve": True, "monthly_limit_days": "1",
        "counts_toward_warning": False,
    }  # fmt: skip
    created = await client.post(
        f"{LEAVE}/policies/{policy.id}/types", json=body, headers=as_user(hr, org)
    )
    assert created.status_code == 201, created.text
    period = created.json()
    assert period["eligibility"] == "women" and period["auto_approve"] is True
    assert Decimal(period["monthly_limit_days"]) == 1
    mon = month_mondays()[0]
    sent = await client.post(
        f"{LEAVE}/requests",
        json={"kind": "leave", "leave_type_id": period["id"], "start_date": mon.isoformat(),
              "end_date": mon.isoformat()},
        headers=as_user(woman, org),
    )  # fmt: skip
    assert sent.status_code == 201, sent.text
    assert sent.json()["status"] == "approved"
    # Switched off, nobody can request it any more.
    off = {**period, "is_active": False}
    updated = await client.put(f"{LEAVE}/types/{period['id']}", json=off, headers=as_user(hr, org))
    assert updated.status_code == 200, updated.text
    async with pg_session_factory() as db:
        summary = await build_summary(db, org, woman, None)
        assert "Period leave" not in {b.leave_type.name for b in summary.balances}


async def test_unpaid_days_still_go_to_a_manager(pg_session_factory: Factory) -> None:
    org, (woman, mgr), _casual = await setup_org(pg_session_factory, "Asha", "Mgr")
    await report_to(pg_session_factory, org, woman, mgr)
    period = await _period_leave(pg_session_factory, org, woman)
    async with pg_session_factory() as db:
        leave_type = await db.get(LeaveType, period)
        assert leave_type is not None
        leave_type.annual_quota_days = Decimal("0")
        await db.commit()
    mon = month_mondays()[0]
    async with pg_session_factory() as db:
        request, _ = await submit(db, org, woman, leave_body(period, mon, mon))
        await db.commit()
        assert request.lop_days == Decimal("1")
        assert request.status == LeaveStatus.PENDING
