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

"""``require_permissions`` against real roles: the owner bypass and custom roles.

The owner bypass is proven on a permission no role holds, so it can only
pass through ``PermissionSet.is_owner``, not through the owner role's
seeded ``*`` grants.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_permissions
from app.models.role import Role, RoleScopeType
from app.repositories.role import RoleRepository
from app.repositories.user import UserRepository
from tests.integration.auth_tenancy_support import add_user, new_tenant
from tests.integration.leave_support import Factory, as_user, give_custom_role, give_role

pytestmark = pytest.mark.integration
NOBODY_HOLDS = "probe:held-by-no-role"


def _probe_app(factory: Factory) -> FastAPI:
    """Two routes gated on a permission that exists in no role."""
    app = FastAPI()

    @app.get("/all", dependencies=[Depends(require_permissions(NOBODY_HOLDS, "team:view"))])
    async def _all() -> dict[str, bool]:
        return {"ok": True}

    @app.get(
        "/any",
        dependencies=[Depends(require_permissions(NOBODY_HOLDS, "team:view", mode="any"))],
    )
    async def _any() -> dict[str, bool]:
        return {"ok": True}

    async def _db() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = _db
    return app


async def test_the_owner_passes_a_check_no_role_could(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """``client`` is requested for its side effect: it seeds the permission catalogue."""
    t = await new_tenant(pg_session_factory)
    admin, _ = await add_user(pg_session_factory, t.org, "admin")
    transport = ASGITransport(app=_probe_app(pg_session_factory))
    async with AsyncClient(transport=transport, base_url="http://probe") as probe:
        owner = as_user(t.owner, t.org)
        assert (await probe.get("/all", headers=owner)).status_code == 200
        assert (await probe.get("/any", headers=owner)).status_code == 200
        # Admin holds team:view but not the probe permission.
        assert (await probe.get("/all", headers=as_user(admin, t.org))).status_code == 403
        assert (await probe.get("/any", headers=as_user(admin, t.org))).status_code == 200
        # Sales holds neither.
        await give_role(pg_session_factory, t.org, t.dev, "sales")
        assert (await probe.get("/any", headers=as_user(t.dev, t.org))).status_code == 403


async def test_a_custom_role_based_on_org_owner_is_not_the_owner(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """Basing a role on ``org_owner`` (e.g. written straight to the DB) grants nothing."""
    t = await new_tenant(pg_session_factory)
    async with pg_session_factory() as db:
        owner_role = await RoleRepository(db).get_by_name_system("org_owner")
        assert owner_role is not None
        shadow = Role(
            name=f"shadow-{uuid.uuid4().hex[:6]}",
            org_id=t.org,
            scope_type=RoleScopeType.CUSTOM,
            base_role_id=owner_role.id,
        )
        db.add(shadow)
        await db.flush()
        membership = await UserRepository(db).get_membership(t.dev, t.org)
        assert membership is not None
        membership.role_id = shadow.id
        await db.commit()
    headers = as_user(t.dev, t.org)
    me = (await client.get("/api/v1/auth/me", headers=headers)).json()
    assert me["permissions"] == []
    for path in ("/api/v1/members", "/api/v1/roles", "/api/v1/features"):
        assert (await client.get(path, headers=headers)).status_code == 403, path
    made = await client.post(
        "/api/v1/roles",
        json={"name": "Escalated", "base_role_id": str(owner_role.id)},
        headers=headers,
    )
    assert made.status_code == 403


async def test_a_custom_role_grants_exactly_what_it_lists(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    t = await new_tenant(pg_session_factory)
    await give_custom_role(pg_session_factory, t.org, t.dev, "team:view")
    headers = as_user(t.dev, t.org)
    me = (await client.get("/api/v1/auth/me", headers=headers)).json()
    assert me["permissions"] == ["team:view"]
    assert (await client.get("/api/v1/roles", headers=headers)).status_code == 200
    assert (await client.get("/api/v1/permissions", headers=headers)).status_code == 200
    # team:manage, team:assign_roles and the engineering workspace aren't listed.
    assert (await client.get("/api/v1/members", headers=headers)).status_code == 403
    assert (await client.get("/api/v1/features", headers=headers)).status_code == 403
    denied = await client.post("/api/v1/roles", json={"name": "x"}, headers=headers)
    assert denied.status_code == 403


async def test_a_member_without_a_role_is_treated_as_a_developer(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    t = await new_tenant(pg_session_factory)
    unassigned, _ = await add_user(pg_session_factory, t.org, None)
    headers = as_user(unassigned, t.org)
    me = (await client.get("/api/v1/auth/me", headers=headers)).json()
    developer = (await client.get("/api/v1/auth/me", headers=as_user(t.dev, t.org))).json()
    assert me["role"] == "developer"
    assert me["permissions"] == developer["permissions"]
    assert (await client.get("/api/v1/features", headers=headers)).status_code == 200
    assert (await client.get("/api/v1/members", headers=headers)).status_code == 403


async def test_system_roles_cannot_be_edited_or_deleted_even_by_the_owner(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    t = await new_tenant(pg_session_factory)
    async with pg_session_factory() as db:
        viewer = await db.scalar(
            select(Role).where(Role.name == "viewer", Role.scope_type == RoleScopeType.SYSTEM)
        )
        assert viewer is not None
    owner = as_user(t.owner, t.org)
    edit = await client.put(f"/api/v1/roles/{viewer.id}", json={"name": "Mine"}, headers=owner)
    assert edit.json() == {"detail": "System roles cannot be modified"}
    gone = await client.delete(f"/api/v1/roles/{viewer.id}", headers=owner)
    assert gone.json() == {"detail": "System roles cannot be deleted"}
    assert (edit.status_code, gone.status_code) == (403, 403)
