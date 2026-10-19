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

"""Permission resolution and the ``require_permissions`` dependency factory.

Import through :mod:`app.core.deps`. Permissions are resolved once per
request by :func:`get_permission_set`: FastAPI caches a dependency by
function identity within a request, so a router-level gate plus a
route-level ``require_permissions`` share one lookup instead of each
querying the role tables.
"""

import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any, Literal

import structlog
from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth_deps import get_current_user, get_db
from app.core.role_defs import DEFAULT_SYSTEM_ROLES
from app.models.role import Role, RoleScopeType
from app.models.user import User
from app.repositories.permission import PermissionRepository
from app.repositories.role import ORG_OWNER_ROLE_NAME, RoleRepository
from app.repositories.user import UserRepository

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class PermissionSet:
    """The caller's effective permissions for one request.

    ``is_owner`` is True only for the seeded SYSTEM ``org_owner`` role,
    which bypasses every check.
    """

    ids: frozenset[str]
    is_owner: bool

    def has(self, permission: str) -> bool:
        """Return True if the caller holds ``permission``."""
        return self.is_owner or permission in self.ids

    def has_all(self, permissions: Iterable[str]) -> bool:
        """Return True if the caller holds every permission listed."""
        return self.is_owner or set(permissions).issubset(self.ids)

    def has_any(self, permissions: Iterable[str]) -> bool:
        """Return True if the caller holds at least one permission listed."""
        return self.is_owner or bool(self.ids.intersection(permissions))


def _is_owner_role(role: Role | None) -> bool:
    return bool(
        role is not None
        and role.scope_type == RoleScopeType.SYSTEM
        and role.name == ORG_OWNER_ROLE_NAME
    )


async def is_org_owner(user: User, db: AsyncSession) -> bool:
    """Return True iff ``user``'s membership role is the SYSTEM ``org_owner``.

    Deliberately ignores ``user.role``: that is the *effective* role, which
    resolves a custom role to its base role's name, so it can't tell the
    real owner apart from a custom role that names ``org_owner`` as base.
    """
    role_ref = getattr(user, "role_ref", None)
    if role_ref is not None:
        return _is_owner_role(role_ref)
    role_id = getattr(user, "role_id", None)
    if role_id is None:
        return False
    return await RoleRepository(db).is_system_owner(role_id)


async def member_has_permission(
    db: AsyncSession, user_id: uuid.UUID, org_id: uuid.UUID, permission: str
) -> bool:
    """Check a permission for a member outside a JWT request.

    For transports that authenticate with their own credential (MCP
    bearer tokens, the Colyseus bridge) and so never run
    :func:`get_permission_set`. Non-members hold nothing.
    """
    pair = await UserRepository(db).get_membership_with_role(user_id, org_id)
    if pair is None:
        return False
    membership, _effective = pair
    if _is_owner_role(membership.role_ref):
        return True
    if membership.role_id is None:
        return False
    return permission in await PermissionRepository(db).get_user_permission_ids(membership.role_id)


async def get_user_permissions(user: User, db: AsyncSession) -> set[str]:
    """Return the set of permission resource_id strings for a user's role.

    Resolves permissions through ``role_id``.  Defence-in-depth: if the
    membership has no ``role_id`` (post-migration this should not happen),
    falls back to the default permission set for the canonical
    :class:`UserRole` carried on ``user.role``.
    """
    role_id = getattr(user, "role_id", None)
    if role_id is not None:
        perm_repo = PermissionRepository(db)
        return await perm_repo.get_user_permission_ids(role_id)

    role_enum = getattr(user, "role", None)
    if role_enum is not None:
        role_name = str(role_enum)
        for role_def in DEFAULT_SYSTEM_ROLES:
            if role_def.name == role_name:
                logger.info(
                    "permissions_from_default_role_set",
                    user_id=str(user.id),
                    role=role_name,
                )
                return set(role_def.permission_ids)

    logger.warning("no_permissions_resolved", user_id=str(user.id))
    return set()


async def get_permission_set(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PermissionSet:
    """Resolve the caller's :class:`PermissionSet` (cached per request)."""
    if await is_org_owner(current_user, db):
        return PermissionSet(ids=frozenset(), is_owner=True)
    ids = await get_user_permissions(current_user, db)
    return PermissionSet(ids=frozenset(ids), is_owner=False)


def require_permissions(
    *permissions: str,
    mode: Literal["all", "any"] = "all",
) -> Callable[..., Any]:
    """FastAPI dependency factory that enforces permission checks.

    Usage::

        @router.get("/", dependencies=[Depends(require_permissions("backlog:view"))])
        @router.post("/approve", dependencies=[Depends(require_permissions("backlog:approve"))])

    Args:
        permissions: One or more permission resource_ids to require.
        mode: "all" requires every listed permission; "any" requires at least one.

    Returns:
        A FastAPI-compatible async dependency function returning the user.
    """
    required = frozenset(permissions)

    async def _check(
        current_user: User = Depends(get_current_user),
        perms: PermissionSet = Depends(get_permission_set),
    ) -> User:
        allowed = perms.has_all(required) if mode == "all" else perms.has_any(required)
        if not allowed:
            logger.warning(
                "permission_denied",
                user_id=str(current_user.id),
                required=sorted(required),
                mode=mode,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions.",
            )
        return current_user

    # Introspection hook for tests that audit which routes are gated.
    _check.required_permissions = required  # type: ignore[attr-defined]
    return _check
