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

"""Grant ceiling: who may hand out which roles and permissions.

Holding ``team:assign_roles`` lets a member manage roles, but never lets
them hand out more access than they hold themselves. Without this rule a
manager could assign themselves ``org_owner`` (or build a custom role
with ``employees:documents``) and walk past every other check.

Same layering as :mod:`app.services.role_validation`: pure predicates
first, thin HTTP wrappers after.
"""

import uuid

import structlog
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permission_deps import PermissionSet
from app.core.permissions import SENSITIVE_PERMISSION_IDS
from app.models.role import Role, RoleScopeType
from app.repositories.permission import PermissionRepository
from app.repositories.role import ORG_OWNER_ROLE_NAME

logger = structlog.get_logger(__name__)


def ungrantable(actor: PermissionSet, requested: set[str]) -> set[str]:
    """Return the permissions in ``requested`` the actor may not grant."""
    if actor.is_owner:
        return set()
    return requested - actor.ids


def is_owner_role(role: Role) -> bool:
    """Return True for the seeded SYSTEM ``org_owner`` role."""
    return role.scope_type == RoleScopeType.SYSTEM and role.name == ORG_OWNER_ROLE_NAME


def assert_can_grant(actor: PermissionSet, requested: set[str]) -> None:
    """Raise 403 unless the actor holds every permission in ``requested``."""
    missing = ungrantable(actor, requested)
    if missing:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "You can only grant permissions you hold yourself. Missing: "
                + ", ".join(sorted(missing))
            ),
        )


async def assert_can_grant_permission_ids(
    db: AsyncSession, actor: PermissionSet, permission_ids: list[uuid.UUID]
) -> set[str]:
    """UUID form of :func:`assert_can_grant`; returns the resolved resource ids."""
    requested = await PermissionRepository(db).resource_ids_for(permission_ids)
    assert_can_grant(actor, requested)
    return requested


async def assert_can_assign_role(
    db: AsyncSession,
    *,
    actor_id: uuid.UUID,
    actor: PermissionSet,
    target_user_id: uuid.UUID | None,
    role: Role,
) -> set[str]:
    """Raise 403 unless the actor may give ``role`` to ``target_user_id``.

    ``target_user_id`` is ``None`` when the target is a member being
    created in the same request. Returns the role's resource ids so the
    caller can log sensitive grants without a second query.
    """
    if target_user_id is not None and target_user_id == actor_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can't change your own role. Ask another admin or the org owner.",
        )
    if is_owner_role(role) and not actor.is_owner:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the org owner can assign the org owner role.",
        )
    role_perms = await PermissionRepository(db).get_user_permission_ids(role.id)
    assert_can_grant(actor, role_perms)
    return role_perms


def log_sensitive_grant(
    *,
    actor_id: uuid.UUID,
    org_id: uuid.UUID,
    granted: set[str],
    target: str,
) -> None:
    """Emit an audit log line when people-data permissions are handed out."""
    sensitive = granted & SENSITIVE_PERMISSION_IDS
    if not sensitive:
        return
    logger.warning(
        "sensitive_permission_granted",
        actor_id=str(actor_id),
        org_id=str(org_id),
        target=target,
        permissions=sorted(sensitive),
    )
