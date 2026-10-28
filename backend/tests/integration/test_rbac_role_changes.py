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

"""Role edits and role assignments apply to a member's very next request.

Permissions are resolved per request, never baked into the token, so the
member keeps the same access token throughout these tests.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.permission import Permission
from app.repositories.role import RoleRepository
from tests.integration.auth_tenancy_support import add_user, new_tenant
from tests.integration.leave_support import Factory, as_user

pytestmark = pytest.mark.integration


async def _permission_ids(factory: Factory, *resource_ids: str) -> list[str]:
    async with factory() as db:
        rows = await db.scalars(select(Permission).where(Permission.resource_id.in_(resource_ids)))
        found = {p.resource_id: str(p.id) for p in rows}
    assert set(found) == set(resource_ids)
    return list(found.values())


async def _sales_base(factory: Factory) -> str:
    """A base role with no permissions, so a custom role holds only what it lists."""
    async with factory() as db:
        sales = await RoleRepository(db).get_by_name_system("sales")
        assert sales is not None
        return str(sales.id)


async def test_editing_a_custom_role_changes_its_holders_access_at_once(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    t = await new_tenant(pg_session_factory)
    owner = as_user(t.owner, t.org)
    made = await client.post(
        "/api/v1/roles",
        json={
            "name": "Team lead",
            "base_role_id": await _sales_base(pg_session_factory),
            "permission_ids": await _permission_ids(pg_session_factory, "team:view"),
        },
        headers=owner,
    )
    assert made.status_code == 201, made.text
    role_id = made.json()["id"]
    given = await client.patch(
        f"/api/v1/members/{t.dev}/role", json={"roleId": role_id}, headers=owner
    )
    assert given.status_code == 200, given.text

    member = as_user(t.dev, t.org)
    assert (await client.get("/api/v1/members", headers=member)).status_code == 403
    wider = await _permission_ids(pg_session_factory, "team:view", "team:manage")
    edited = await client.put(
        f"/api/v1/roles/{role_id}", json={"permission_ids": wider}, headers=owner
    )
    assert edited.status_code == 200, edited.text
    assert (await client.get("/api/v1/members", headers=member)).status_code == 200
    me = (await client.get("/api/v1/auth/me", headers=member)).json()
    assert me["permissions"] == ["team:manage", "team:view"]

    narrower = await _permission_ids(pg_session_factory, "team:view")
    await client.put(f"/api/v1/roles/{role_id}", json={"permission_ids": narrower}, headers=owner)
    assert (await client.get("/api/v1/members", headers=member)).status_code == 403


async def test_assigning_a_system_role_applies_on_the_next_request(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    t = await new_tenant(pg_session_factory)
    member = as_user(t.dev, t.org)
    assert (await client.get("/api/v1/features", headers=member)).status_code == 200
    async with pg_session_factory() as db:
        hr = await RoleRepository(db).get_by_name_system("hr")
        assert hr is not None
    owner = as_user(t.owner, t.org)
    given = await client.patch(
        f"/api/v1/members/{t.dev}/role", json={"roleId": str(hr.id)}, headers=owner
    )
    assert given.status_code == 200, given.text
    # HR is people-only: the engineering workspace closes, employee records open.
    assert (await client.get("/api/v1/features", headers=member)).status_code == 403
    record = await client.get(f"/api/v1/employees/{t.owner}", headers=member)
    assert record.status_code == 200, record.text


async def test_nobody_but_the_owner_edits_the_role_they_hold(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    t = await new_tenant(pg_session_factory)
    owner = as_user(t.owner, t.org)
    perms = await _permission_ids(
        pg_session_factory, "team:view", "team:manage", "team:assign_roles"
    )
    made = await client.post(
        "/api/v1/roles",
        json={
            "name": "Role admin",
            "base_role_id": await _sales_base(pg_session_factory),
            "permission_ids": perms,
        },
        headers=owner,
    )
    assert made.status_code == 201, made.text
    role_id = made.json()["id"]
    other = await client.post(
        "/api/v1/roles",
        json={
            "name": "Viewer of team",
            "base_role_id": await _sales_base(pg_session_factory),
            "permission_ids": await _permission_ids(pg_session_factory, "team:view"),
        },
        headers=owner,
    )
    assert other.status_code == 201, other.text
    given = await client.patch(
        f"/api/v1/members/{t.dev}/role", json={"roleId": role_id}, headers=owner
    )
    assert given.status_code == 200, given.text
    colleague, _ = await add_user(pg_session_factory, t.org, "sales")
    dev = as_user(t.dev, t.org)

    own_edit = await client.put(
        f"/api/v1/roles/{role_id}", json={"name": "Self-promoted"}, headers=dev
    )
    assert own_edit.status_code == 403
    own_role = await client.patch(
        f"/api/v1/members/{t.dev}/role", json={"roleId": role_id}, headers=dev
    )
    assert own_role.status_code == 403
    # Control: the same member can edit and hand out a role they don't hold.
    other_id = other.json()["id"]
    edited = await client.put(f"/api/v1/roles/{other_id}", json={"name": "Renamed"}, headers=dev)
    assert edited.status_code == 200, edited.text
    handed = await client.patch(
        f"/api/v1/members/{colleague}/role", json={"roleId": other_id}, headers=dev
    )
    assert handed.status_code == 200, handed.text


async def test_a_role_admin_cannot_promote_anyone_to_owner(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    t = await new_tenant(pg_session_factory)
    admin, _ = await add_user(pg_session_factory, t.org, "admin")
    async with pg_session_factory() as db:
        owner_role = await RoleRepository(db).get_by_name_system("org_owner")
        assert owner_role is not None
    tried = await client.patch(
        f"/api/v1/members/{t.dev}/role",
        json={"roleId": str(owner_role.id)},
        headers=as_user(admin, t.org),
    )
    assert tried.status_code == 403
    assert tried.json() == {"detail": "Only the org owner can assign the org owner role."}
    on_owner = await client.patch(
        f"/api/v1/members/{t.owner}/status", headers=as_user(admin, t.org)
    )
    assert on_owner.status_code == 403
