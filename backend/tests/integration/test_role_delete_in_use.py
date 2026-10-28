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

"""Deleting a custom role that members still hold is refused, not a server error."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient

from app.models.role import Role
from app.models.user import User
from app.repositories.role import RoleRepository
from app.repositories.user import UserRepository
from tests.integration.leave_support import (
    Factory,
    as_user,
    give_custom_role,
    give_role,
    setup_org,
)

pytestmark = pytest.mark.integration


async def _held_role(
    factory: Factory, *, deactivate: bool = False
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    """An org, its owner, a member and the custom role that member holds."""
    org, (owner, holder), _ = await setup_org(factory, "Owner", "Holder")
    await give_role(factory, org, owner, "org_owner")
    await give_custom_role(factory, org, holder, "team:view")
    async with factory() as db:
        membership = await UserRepository(db).get_membership(holder, org)
        assert membership is not None and membership.role_id is not None
        user = await db.get(User, holder)
        assert user is not None
        user.is_active = not deactivate
        await db.commit()
        return org, owner, holder, membership.role_id


async def _role_exists(factory: Factory, role_id: uuid.UUID) -> bool:
    async with factory() as db:
        return await db.get(Role, role_id) is not None


async def test_a_held_role_is_kept_until_nobody_holds_it(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, owner, holder, role_id = await _held_role(pg_session_factory)
    headers = as_user(owner, org)

    refused = await client.delete(f"/api/v1/roles/{role_id}", headers=headers)
    assert refused.status_code == 409
    assert refused.json() == {
        "detail": "1 member(s) still have this role. Give them another role first."
    }
    assert await _role_exists(pg_session_factory, role_id)

    await give_role(pg_session_factory, org, holder, "developer")
    deleted = await client.delete(f"/api/v1/roles/{role_id}", headers=headers)
    assert deleted.status_code == 204
    assert not await _role_exists(pg_session_factory, role_id)


async def test_a_deactivated_member_still_holding_the_role_blocks_the_delete(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """Reactivating them brings their role back, so it can't vanish meanwhile."""
    org, owner, _holder, role_id = await _held_role(pg_session_factory, deactivate=True)
    refused = await client.delete(f"/api/v1/roles/{role_id}", headers=as_user(owner, org))
    assert refused.status_code == 409
    assert await _role_exists(pg_session_factory, role_id)


async def test_a_role_given_out_after_the_count_is_still_refused(
    client: AsyncClient, pg_session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The count can miss a concurrent assignment; the foreign key has the last word."""
    org, owner, _holder, role_id = await _held_role(pg_session_factory)
    monkeypatch.setattr(RoleRepository, "count_holders", AsyncMock(return_value=0))
    raced = await client.delete(f"/api/v1/roles/{role_id}", headers=as_user(owner, org))
    assert raced.status_code == 409
    assert raced.json() == {
        "detail": "A member was just given this role. Give them another role first."
    }
    assert await _role_exists(pg_session_factory, role_id)
