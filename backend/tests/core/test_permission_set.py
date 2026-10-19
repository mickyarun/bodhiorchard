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

"""Owner detection and the people-workspace role catalog."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.core.deps import PermissionSet, is_org_owner
from app.core.permissions import SENSITIVE_PERMISSION_IDS, WORKSPACE_ENGINEERING
from app.core.role_defs import DEFAULT_SYSTEM_ROLES, RESERVED_ROLE_NAMES
from app.models.role import RoleScopeType

ROLES = {r.name: set(r.permission_ids) for r in DEFAULT_SYSTEM_ROLES}


def _user(name: str, scope: RoleScopeType) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        role_id=uuid.uuid4(),
        role_ref=SimpleNamespace(name=name, scope_type=scope),
    )


async def test_system_org_owner_is_owner() -> None:
    assert await is_org_owner(_user("org_owner", RoleScopeType.SYSTEM), AsyncMock()) is True


async def test_custom_role_named_org_owner_is_not_owner() -> None:
    assert await is_org_owner(_user("org_owner", RoleScopeType.CUSTOM), AsyncMock()) is False


def test_owner_permission_set_passes_every_check() -> None:
    owner = PermissionSet(ids=frozenset(), is_owner=True)
    assert owner.has("employees:documents")
    assert owner.has_all({"leave:approve", "buds:view"})


def test_every_existing_role_keeps_engineering_access() -> None:
    for name, perms in ROLES.items():
        if name in {"hr", "sales"}:
            continue
        assert WORKSPACE_ENGINEERING in perms, f"{name} lost engineering access"


def test_sales_role_has_no_permissions() -> None:
    assert ROLES["sales"] == set()


def test_hr_role_is_people_only() -> None:
    assert WORKSPACE_ENGINEERING not in ROLES["hr"]
    assert ROLES["hr"] >= SENSITIVE_PERMISSION_IDS


def test_admin_cannot_see_leave_reasons_or_employee_documents() -> None:
    assert "leave:approve" not in ROLES["admin"]
    assert "employees:documents" not in ROLES["admin"]
    assert "employees:manage" not in ROLES["admin"]


def test_sensitive_permission_holders() -> None:
    holders = {name for name, perms in ROLES.items() if perms & SENSITIVE_PERMISSION_IDS}
    assert holders == {"org_owner", "hr", "admin"}
    # admin holds leave:configure only, which carries no personal data.
    assert ROLES["admin"] & SENSITIVE_PERMISSION_IDS == {"leave:configure"}


def test_system_role_names_are_reserved() -> None:
    assert {"org_owner", "hr", "sales"} <= RESERVED_ROLE_NAMES
