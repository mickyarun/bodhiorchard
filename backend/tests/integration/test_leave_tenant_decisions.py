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

"""Who may decide, over HTTP: HR rights never cross orgs, and HR never decides their own."""

from __future__ import annotations

import uuid
from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.leave_ledger import LeaveLedgerEntry, LedgerEntryType
from app.models.leave_request import LeaveStatus
from app.models.policy_holiday import PolicyHoliday
from app.models.user import OrgToUser
from app.services.leave.policies import ensure_default_policy
from tests.integration.leave_edge_support import freeze_today, quiet_notifications, stored
from tests.integration.leave_support import Factory, as_user, give_role, report_to, setup_org

pytestmark = pytest.mark.integration
LEAVE = "/api/v1/leave"
TODAY = date(2030, 6, 3)  # a Monday
DAY = "2030-06-11"
HOLIDAY = {"date": DAY, "name": "Not yours"}


@pytest.fixture(autouse=True)
def _frozen(monkeypatch: pytest.MonkeyPatch) -> None:
    freeze_today(monkeypatch, TODAY)
    quiet_notifications(monkeypatch)


def _body(type_id: uuid.UUID) -> dict[str, str]:
    return {"kind": "leave", "leave_type_id": str(type_id), "start_date": DAY, "end_date": DAY}


async def _submit(client: AsyncClient, org: uuid.UUID, user: uuid.UUID, type_id: uuid.UUID) -> str:
    response = await client.post(
        f"{LEAVE}/requests", json=_body(type_id), headers=as_user(user, org)
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


async def _policy_of(factory: Factory, org: uuid.UUID) -> uuid.UUID:
    async with factory() as db:
        return (await ensure_default_policy(db, org)).id


async def _join(factory: Factory, user: uuid.UUID, org: uuid.UUID) -> None:
    """Make ``user`` a plain member of a second org too."""
    async with factory() as db:
        db.add(OrgToUser(user_id=user, org_id=org))
        await db.commit()


async def test_hr_of_another_org_cannot_touch_this_orgs_leave_balances_or_holidays(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """Full HR rights in their own org, none here: a plain stranger is covered elsewhere."""
    org, (emp, mgr), casual = await setup_org(pg_session_factory, "Emp", "Mgr")
    other, (outsider,), _ = await setup_org(pg_session_factory, "OutsideHr")
    await give_role(pg_session_factory, other, outsider, "hr")
    await report_to(pg_session_factory, org, emp, mgr)
    request_id = await _submit(client, org, emp, casual)
    headers = as_user(outsider, other)
    calls = (
        (f"requests/{request_id}/approve", {}),
        (f"requests/{request_id}/reject", {"note": "No"}),
        (
            f"balances/{emp}/adjust",
            {"leave_type_id": str(casual), "days": "5", "note": "Bonus", "leave_year": 2030},
        ),
        (f"policies/{await _policy_of(pg_session_factory, org)}/holidays", HOLIDAY),
    )
    for path, body in calls:
        response = await client.post(f"{LEAVE}/{path}", json=body, headers=headers)
        assert response.status_code == 404, (path, response.text)
    assert (await stored(pg_session_factory, uuid.UUID(request_id))).status == LeaveStatus.PENDING
    async with pg_session_factory() as db:
        ledger = await db.scalars(select(LeaveLedgerEntry).where(LeaveLedgerEntry.user_id == emp))
        assert [e.entry_type for e in ledger] == [LedgerEntryType.ALLOCATION]
        holidays = await db.scalars(select(PolicyHoliday).where(PolicyHoliday.org_id == org))
        assert list(holidays) == []


async def test_hr_rights_in_one_org_do_not_follow_the_user_into_another(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """HR in org B who is a plain member of org A can't decide org A's leave."""
    org, (emp, mgr), casual = await setup_org(pg_session_factory, "Emp", "Mgr")
    other, (dual,), _ = await setup_org(pg_session_factory, "Dual")
    await give_role(pg_session_factory, other, dual, "hr")
    await _join(pg_session_factory, dual, org)
    await report_to(pg_session_factory, org, emp, mgr)
    request_id = await _submit(client, org, emp, casual)
    approve = f"{LEAVE}/requests/{request_id}/approve"
    as_member = await client.post(approve, json={}, headers=as_user(dual, org))
    assert as_member.status_code == 403
    as_hr_elsewhere = await client.post(approve, json={}, headers=as_user(dual, other))
    assert as_hr_elsewhere.status_code == 404
    assert (await stored(pg_session_factory, uuid.UUID(request_id))).status == LeaveStatus.PENDING


async def test_the_only_hr_without_a_manager_has_nobody_to_approve_them(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, (hr1, hr2), casual = await setup_org(pg_session_factory, "Hr1", "Hr2")
    await give_role(pg_session_factory, org, hr1, "hr")
    preview = await client.post(
        f"{LEAVE}/requests/preview", json=_body(casual), headers=as_user(hr1, org)
    )
    assert preview.status_code == 200
    assert [p["code"] for p in preview.json()["problems"]] == ["no_approver"]
    refused = await client.post(f"{LEAVE}/requests", json=_body(casual), headers=as_user(hr1, org))
    assert refused.status_code == 409

    # A second HR can approve them, but they still can't approve themselves.
    await give_role(pg_session_factory, org, hr2, "hr")
    request_id = await _submit(client, org, hr1, casual)
    approve = f"{LEAVE}/requests/{request_id}/approve"
    own = await client.post(approve, json={}, headers=as_user(hr1, org))
    assert own.status_code == 403
    assert "your own" in own.json()["detail"]
    other_hr = await client.post(approve, json={}, headers=as_user(hr2, org))
    assert other_hr.status_code == 200 and other_hr.json()["status"] == "approved"
    decided = await stored(pg_session_factory, uuid.UUID(request_id))
    assert decided.decided_by == hr2


async def test_hr_overrides_a_manager_but_the_first_decision_still_wins(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, (emp, mgr, hr), casual = await setup_org(pg_session_factory, "Emp", "Mgr", "Hr")
    await give_role(pg_session_factory, org, hr, "hr")
    await report_to(pg_session_factory, org, emp, mgr)
    request_id = await _submit(client, org, emp, casual)
    rejected = await client.post(
        f"{LEAVE}/requests/{request_id}/reject",
        json={"note": "Quarter close"},
        headers=as_user(hr, org),
    )
    assert rejected.status_code == 200 and rejected.json()["status"] == "rejected"
    late = await client.post(
        f"{LEAVE}/requests/{request_id}/approve", json={}, headers=as_user(mgr, org)
    )
    assert late.status_code == 409
    assert "rejected" in late.json()["detail"]
    decided = await stored(pg_session_factory, uuid.UUID(request_id))
    assert (decided.status, decided.decided_by) == (LeaveStatus.REJECTED, hr)
