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

"""HR tools: recalculating a frozen allocation, the configuration trail,
and the submit throttle."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient

from app.models.leave_ledger import LedgerEntryType
from app.models.leave_policy import ProrationMethod
from app.repositories.employee_profile import EmployeeProfileRepository
from app.repositories.leave_ledger import LeaveLedgerRepository
from app.services.leave import adjustments, lifecycle
from app.services.leave.errors import LeaveConflictError, LeaveForbiddenError
from app.services.leave.lifecycle import submit
from app.services.leave.policies import resolve_member_policy
from tests.integration.leave_support import (
    Factory,
    as_user,
    future_monday,
    give_role,
    leave_body,
    report_to,
    setup_org,
)

pytestmark = pytest.mark.integration
LEAVE = "/api/v1/leave"


def _change(
    org: uuid.UUID, actor: uuid.UUID, user: uuid.UUID, type_id: uuid.UUID, year: int
) -> adjustments.BalanceChange:
    return adjustments.BalanceChange(
        org_id=org,
        actor_id=actor,
        actor_is_owner=False,
        user_id=user,
        leave_type_id=type_id,
        leave_year=year,
        sees_restricted=False,
    )


async def test_recalculating_books_the_gap_once(pg_session_factory: Factory) -> None:
    org, (emp, mgr, hr), casual = await setup_org(pg_session_factory, "Emp", "Mgr", "Hr")
    await report_to(pg_session_factory, org, emp, mgr)
    mon = future_monday()
    async with pg_session_factory() as db:
        # No joining date yet: the first request freezes the full 5 days.
        await submit(db, org, emp, leave_body(casual, mon, mon))
        await db.commit()
    async with pg_session_factory() as db:
        # HR then records a mid-year joining date and monthly proration.
        policy = (await resolve_member_policy(db, org, emp)).policy
        policy.proration_method = ProrationMethod.MONTHLY
        profile = await EmployeeProfileRepository(db, org_id=org).get_by_user(emp)
        assert profile is not None
        profile.date_of_joining = date(mon.year, 7, 20)
        await db.commit()
    change = _change(org, hr, emp, casual, mon.year)
    async with pg_session_factory() as db:
        first = await adjustments.recalculate(db, change)
        await db.commit()
    # Aug to Dec: 5 x 5 / 12 = 2.08, to the nearest half day.
    assert (first.frozen, first.recalculated, first.correction) == (
        Decimal("5"),
        Decimal("2.0"),
        Decimal("-3.0"),
    )
    async with pg_session_factory() as db:
        again = await adjustments.recalculate(db, change)
        await db.commit()
        entries = await LeaveLedgerRepository(db, org_id=org).list_for(emp, mon.year)
    assert again.correction == Decimal("0")
    corrections = [e for e in entries if e.entry_type == LedgerEntryType.CORRECTION]
    assert [(e.days, e.created_by) for e in corrections] == [(Decimal("-3.0"), hr)]


async def test_recalculating_needs_a_frozen_year_and_someone_else(
    pg_session_factory: Factory,
) -> None:
    org, (emp, hr), casual = await setup_org(pg_session_factory, "Emp", "Hr")
    year = future_monday().year
    async with pg_session_factory() as db:
        with pytest.raises(LeaveConflictError):
            await adjustments.recalculate(db, _change(org, hr, emp, casual, year))
    async with pg_session_factory() as db:
        with pytest.raises(LeaveForbiddenError):
            await adjustments.recalculate(db, _change(org, hr, hr, casual, year))


async def test_config_changes_are_traced_with_who_and_what(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, (admin,), casual = await setup_org(pg_session_factory, "Admin")
    await give_role(pg_session_factory, org, admin, "admin")
    headers = as_user(admin, org)
    policies = (await client.get(f"{LEAVE}/policies", headers=headers)).json()
    policy = policies[0]
    changed = {**policy, "proration_method": "monthly", "proration_cutoff_day": 10}
    response = await client.put(f"{LEAVE}/policies/{policy['id']}", json=changed, headers=headers)
    assert response.status_code == 200, response.text
    leave_type = (
        await client.get(f"{LEAVE}/policies/{policy['id']}/types", headers=headers)
    ).json()[0]
    raised = {**leave_type, "annual_quota_days": "12"}
    response = await client.put(f"{LEAVE}/types/{casual}", json=raised, headers=headers)
    assert response.status_code == 200, response.text

    history = (
        await client.get(f"{LEAVE}/policies/{policy['id']}/history", headers=headers)
    ).json()
    assert [e["action"] for e in history] == ["type_updated", "policy_updated"]
    assert history[0]["actor"]["name"] == "Admin"
    assert history[0]["changes"] == {"type": "CL", "annual_quota_days": ["5", "12"]}
    assert history[1]["changes"] == {
        "proration_method": ["daily", "monthly"],
        "proration_cutoff_day": [15, 10],
    }


async def test_unchanged_saves_leave_no_trace(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, (admin,), _ = await setup_org(pg_session_factory, "Admin")
    await give_role(pg_session_factory, org, admin, "admin")
    headers = as_user(admin, org)
    policy = (await client.get(f"{LEAVE}/policies", headers=headers)).json()[0]
    base = f"{LEAVE}/policies/{policy['id']}"
    await client.put(base, json=policy, headers=headers)
    leave_type = (await client.get(f"{base}/types", headers=headers)).json()[0]
    # The dialog sends the quota as a number (5), the database holds 5.0.
    same = {**leave_type, "annual_quota_days": 5}
    assert (
        await client.put(f"{LEAVE}/types/{leave_type['id']}", json=same, headers=headers)
    ).is_success
    history = await client.get(f"{base}/history", headers=headers)
    assert history.json() == []


async def test_too_many_requests_are_throttled(
    client: AsyncClient, pg_session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    org, (emp, mgr), casual = await setup_org(pg_session_factory, "Emp", "Mgr")
    await report_to(pg_session_factory, org, emp, mgr)
    monkeypatch.setattr(lifecycle, "seconds_until_allowed", AsyncMock(return_value=42))
    day = future_monday().isoformat()
    body = {"kind": "leave", "leave_type_id": str(casual), "start_date": day, "end_date": day}
    response = await client.post(f"{LEAVE}/requests", json=body, headers=as_user(emp, org))
    assert response.status_code == 429
    assert response.headers["retry-after"] == "42"
