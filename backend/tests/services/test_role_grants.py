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

"""Grant ceiling: nobody hands out more access than they hold.

Pins the escalation paths found in review: a ``team:assign_roles``
holder assigning themselves ``org_owner``, assigning a role whose
permissions exceed their own, or changing their own role.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.core.deps import PermissionSet
from app.models.role import RoleScopeType
from app.services import role_grants
from app.services.role_grants import assert_can_assign_role, assert_can_grant, ungrantable

MANAGER = PermissionSet(
    ids=frozenset({"team:assign_roles", "buds:view", "workspace:engineering"}),
    is_owner=False,
)
OWNER = PermissionSet(ids=frozenset(), is_owner=True)


def _role(name: str, scope: RoleScopeType = RoleScopeType.SYSTEM) -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), name=name, scope_type=scope)


def _patch_role_perms(monkeypatch: pytest.MonkeyPatch, perms: set[str]) -> None:
    repo = MagicMock(get_user_permission_ids=AsyncMock(return_value=perms))
    monkeypatch.setattr(role_grants, "PermissionRepository", MagicMock(return_value=repo))


def test_ungrantable_lists_permissions_the_actor_lacks() -> None:
    assert ungrantable(MANAGER, {"buds:view", "employees:documents"}) == {"employees:documents"}


def test_owner_can_grant_anything() -> None:
    assert ungrantable(OWNER, {"employees:documents", "leave:approve"}) == set()


def test_assert_can_grant_names_missing_permissions() -> None:
    with pytest.raises(HTTPException) as excinfo:
        assert_can_grant(MANAGER, {"employees:documents"})
    assert excinfo.value.status_code == 403
    assert "employees:documents" in excinfo.value.detail


async def test_cannot_change_own_role(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_role_perms(monkeypatch, {"buds:view"})
    actor_id = uuid.uuid4()
    with pytest.raises(HTTPException) as excinfo:
        await assert_can_assign_role(
            AsyncMock(), actor_id=actor_id, actor=OWNER, target_user_id=actor_id, role=_role("pm")
        )
    assert excinfo.value.status_code == 403


async def test_non_owner_cannot_assign_owner_role(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_role_perms(monkeypatch, set())
    with pytest.raises(HTTPException) as excinfo:
        await assert_can_assign_role(
            AsyncMock(),
            actor_id=uuid.uuid4(),
            actor=MANAGER,
            target_user_id=uuid.uuid4(),
            role=_role("org_owner"),
        )
    assert excinfo.value.status_code == 403
    assert "org owner" in excinfo.value.detail


async def test_custom_role_named_org_owner_is_not_the_owner_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Only the SYSTEM row is the owner; a custom role with that name is
    # judged by its permissions like any other role.
    _patch_role_perms(monkeypatch, {"buds:view"})
    granted = await assert_can_assign_role(
        AsyncMock(),
        actor_id=uuid.uuid4(),
        actor=MANAGER,
        target_user_id=uuid.uuid4(),
        role=_role("org_owner", RoleScopeType.CUSTOM),
    )
    assert granted == {"buds:view"}


async def test_cannot_assign_role_exceeding_own_permissions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_role_perms(monkeypatch, {"buds:view", "employees:documents"})
    with pytest.raises(HTTPException) as excinfo:
        await assert_can_assign_role(
            AsyncMock(),
            actor_id=uuid.uuid4(),
            actor=MANAGER,
            target_user_id=uuid.uuid4(),
            role=_role("hr"),
        )
    assert excinfo.value.status_code == 403


async def test_can_assign_role_within_own_permissions(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_role_perms(monkeypatch, {"buds:view"})
    granted = await assert_can_assign_role(
        AsyncMock(),
        actor_id=uuid.uuid4(),
        actor=MANAGER,
        target_user_id=None,
        role=_role("viewer"),
    )
    assert granted == {"buds:view"}
