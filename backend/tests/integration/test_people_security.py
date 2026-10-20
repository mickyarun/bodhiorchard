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

"""Regression tests for the people-module security review.

Each test is an attack that used to work: taking over an employee's
identity to read their HR data, reading balances through a write route,
reading another org, and stripping or minting roles above your access.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.permission import Permission
from app.repositories.role import RoleRepository
from tests.integration.leave_support import (
    Factory,
    as_user,
    future_monday,
    give_custom_role,
    give_role,
    report_to,
    setup_org,
)

pytestmark = pytest.mark.integration
HR_PERMS = ("employees:view", "employees:manage", "employees:documents", "leave:approve")


async def _permission_ids(factory: Factory, *resource_ids: str) -> list[str]:
    async with factory() as db:
        rows = await db.scalars(select(Permission).where(Permission.resource_id.in_(resource_ids)))
        return [str(p.id) for p in rows]


async def test_a_manager_cannot_take_over_someone_with_an_employee_record(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, (emp, owner, mgr), _ = await setup_org(pg_session_factory, "Emp", "Owner", "Mgr")
    await give_role(pg_session_factory, org, owner, "org_owner")
    await give_role(pg_session_factory, org, emp, "developer")
    await give_role(pg_session_factory, org, mgr, "manager")
    # Merging them into yourself would hand you their record.
    merge = await client.post(
        f"/api/v1/members/{mgr}/merge", json={"sourceId": str(emp)}, headers=as_user(mgr, org)
    )
    assert merge.status_code == 403
    # A temporary password would let them sign in as the employee.
    reset = await client.post(f"/api/v1/members/{emp}/set-password", headers=as_user(mgr, org))
    assert reset.status_code == 403
    assert "employee record" in reset.json()["detail"]
    allowed = await client.post(f"/api/v1/members/{emp}/set-password", headers=as_user(owner, org))
    assert allowed.status_code == 200, allowed.text


async def test_leave_configure_alone_does_not_reveal_balances(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, (emp, admin), casual = await setup_org(pg_session_factory, "Emp", "Admin")
    await give_role(pg_session_factory, org, admin, "admin")
    body = {"leave_type_id": str(casual)}
    recalc = await client.post(
        f"/api/v1/leave/balances/{emp}/recalculate", json=body, headers=as_user(admin, org)
    )
    adjust = await client.post(
        f"/api/v1/leave/balances/{emp}/adjust",
        json={**body, "days": "1", "note": "Carry forward"},
        headers=as_user(admin, org),
    )
    assert (recalc.status_code, adjust.status_code) == (403, 403)
    zero = await client.post(
        f"/api/v1/leave/balances/{emp}/adjust",
        json={**body, "days": str(Decimal(0)), "note": "Nothing"},
        headers=as_user(admin, org),
    )
    assert zero.status_code == 422


async def test_another_org_is_not_found_and_members_cannot_create_orgs(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, (dev,), _ = await setup_org(pg_session_factory, "Dev")
    await give_role(pg_session_factory, org, dev, "developer")
    other, _, _ = await setup_org(pg_session_factory, "Other")
    theirs = await client.get(f"/api/v1/organizations/{other}", headers=as_user(dev, org))
    assert theirs.status_code == 404
    own = await client.get(f"/api/v1/organizations/{org}", headers=as_user(dev, org))
    assert own.status_code == 200
    slug = f"mint-{uuid.uuid4().hex[:8]}"
    minted = await client.post(
        "/api/v1/organizations/", json={"name": "Mint", "slug": slug}, headers=as_user(dev, org)
    )
    assert minted.status_code == 403


async def test_roles_above_your_access_cannot_be_changed_or_minted(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, (hr_lead, mgr), _ = await setup_org(pg_session_factory, "HrLead", "Mgr")
    await give_role(pg_session_factory, org, mgr, "manager")
    await give_custom_role(pg_session_factory, org, hr_lead, *HR_PERMS)
    async with pg_session_factory() as db:
        membership_role = await RoleRepository(db, org_id=org).list_active()
        role_id = next(r.id for r in membership_role if r.name.startswith("custom-"))
        hr_base = await RoleRepository(db).get_by_name_system("hr")
        assert hr_base is not None
    workspace = await _permission_ids(pg_session_factory, "workspace:engineering")
    edit = await client.put(
        f"/api/v1/roles/{role_id}", json={"permission_ids": workspace}, headers=as_user(mgr, org)
    )
    delete = await client.delete(f"/api/v1/roles/{role_id}", headers=as_user(mgr, org))
    assert (edit.status_code, delete.status_code) == (403, 403)
    # Basing a new role on HR would carry HR's effective role name.
    minted = await client.post(
        "/api/v1/roles",
        json={"name": "Shadow HR", "base_role_id": str(hr_base.id), "permission_ids": workspace},
        headers=as_user(mgr, org),
    )
    assert minted.status_code == 403


async def test_a_sales_user_has_leave_and_their_own_record_only(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, (seller, mgr), casual = await setup_org(pg_session_factory, "Seller", "Mgr")
    await give_role(pg_session_factory, org, seller, "sales")
    await report_to(pg_session_factory, org, seller, mgr)
    headers = as_user(seller, org)
    day = future_monday().isoformat()
    body = {"kind": "leave", "leave_type_id": str(casual), "start_date": day, "end_date": day}
    sent = await client.post("/api/v1/leave/requests", json=body, headers=headers)
    assert sent.status_code == 201, sent.text
    assert (await client.get("/api/v1/leave/me/summary", headers=headers)).status_code == 200
    assert (await client.get("/api/v1/employees/me", headers=headers)).status_code == 200
    for engineering in ("/api/v1/features", "/api/v1/bugs", "/api/v1/me/mcp-tokens"):
        assert (await client.get(engineering, headers=headers)).status_code == 403, engineering
    assert (await client.get(f"/api/v1/employees/{mgr}", headers=headers)).status_code == 403
