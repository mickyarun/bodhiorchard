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

"""Who can assign which system role, computed from the real role catalog.

Pins the day-to-day duties the grant ceiling must not break (a manager
staffing developers and QA, an admin appointing the quiz master) alongside
the escalations it must stop (anyone but the owner creating admins or HR,
HR handing out engineering access).
"""

import pytest

from app.core.deps import PermissionSet
from app.core.role_defs import DEFAULT_SYSTEM_ROLES
from app.services.role_grants import ungrantable

ROLES = {r.name: set(r.permission_ids) for r in DEFAULT_SYSTEM_ROLES}


def _can_assign(assigner: str, role: str) -> bool:
    actor = PermissionSet(ids=frozenset(ROLES[assigner]), is_owner=assigner == "org_owner")
    return not ungrantable(actor, ROLES[role])


@pytest.mark.parametrize(
    "role", ["developer", "designer", "qa", "support", "pm", "tech_lead", "viewer", "sales"]
)
def test_manager_can_staff_working_roles(role: str) -> None:
    assert _can_assign("manager", role)


@pytest.mark.parametrize("role", ["admin", "hr"])
def test_manager_cannot_create_admins_or_hr(role: str) -> None:
    assert not _can_assign("manager", role)


def test_admin_can_appoint_quiz_master() -> None:
    assert _can_assign("admin", "quiz_master")


def test_admin_cannot_create_hr() -> None:
    assert not _can_assign("admin", "hr")


def test_hr_assigns_every_role_but_admin_level_ones() -> None:
    # HR invites, so it can hand out engineering access...
    for role in ("sales", "hr", "developer", "qa", "pm", "tech_lead", "designer"):
        assert _can_assign("hr", role), role
    # ...but never a role that manages members, roles or settings.
    for role in ("admin", "manager", "org_owner"):
        assert not _can_assign("hr", role), role


@pytest.mark.parametrize("role", sorted(ROLES))
def test_owner_can_assign_every_role(role: str) -> None:
    assert _can_assign("org_owner", role)
