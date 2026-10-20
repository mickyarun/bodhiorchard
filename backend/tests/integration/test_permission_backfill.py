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

"""Custom roles that existed before the engineering workspace gate keep their access."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import delete, select

from app.models.permission import Permission
from app.models.role import RolePermission
from app.repositories.user import UserRepository
from app.services.permission_seeder import seed_permissions
from tests.integration.leave_support import Factory, give_custom_role, setup_org

pytestmark = pytest.mark.integration
GATE = "workspace:engineering"


async def _role_perms(factory: Factory, org: uuid.UUID, user: uuid.UUID) -> set[str]:
    async with factory() as db:
        membership = await UserRepository(db).get_membership(user, org)
        assert membership is not None and membership.role_id is not None
        rows = await db.scalars(
            select(Permission.resource_id)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .where(RolePermission.role_id == membership.role_id)
        )
        return set(rows)


async def test_the_gate_reaches_existing_custom_roles_only_once(
    pg_session_factory: Factory,
) -> None:
    org, (before, after), _ = await setup_org(pg_session_factory, "Before", "After")
    async with pg_session_factory() as db:
        # An install from before the gate: no such permission yet.
        gate = (await db.scalars(select(Permission).where(Permission.resource_id == GATE))).one()
        await db.execute(delete(RolePermission).where(RolePermission.permission_id == gate.id))
        await db.delete(gate)
        await db.commit()
    await give_custom_role(pg_session_factory, org, before, "knowledge:view")
    async with pg_session_factory() as db:
        await seed_permissions(db)
        await db.commit()
    assert GATE in await _role_perms(pg_session_factory, org, before)
    # A role made after the upgrade (say, for sales) isn't touched by later boots.
    await give_custom_role(pg_session_factory, org, after, "knowledge:view")
    async with pg_session_factory() as db:
        await seed_permissions(db)
        await db.commit()
    assert GATE not in await _role_perms(pg_session_factory, org, after)
