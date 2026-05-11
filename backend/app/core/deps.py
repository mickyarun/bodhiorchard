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

"""FastAPI dependency injection providers."""

import uuid
from collections.abc import AsyncGenerator, Callable
from typing import Literal

import structlog
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_token
from app.database import AsyncSessionLocal
from app.models.user import OrgToUser, User, UserRole
from app.repositories.permission import PermissionRepository
from app.repositories.role import RoleRepository
from app.repositories.user import UserRepository

logger = structlog.get_logger(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session scoped to a single request.

    Commits on success, rolls back on exception, and always closes.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Resolve the current authenticated user from the JWT bearer token.

    Extracts user_id and org_id from the JWT, validates OrgToUser membership,
    and sets transient org_id/role/role_id attributes on the User instance.

    Args:
        token: The JWT bearer token extracted from the Authorization header.
        db: The async database session.

    Returns:
        The authenticated User ORM instance with org context set.

    Raises:
        HTTPException: If the token is invalid, user does not exist,
            or user is not a member of the org in the token.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    payload = verify_token(token)
    if payload is None:
        raise credentials_exception

    user_id_str: str | None = payload.get("sub")
    org_id_str: str | None = payload.get("org_id")
    if user_id_str is None or org_id_str is None:
        raise credentials_exception

    try:
        user_id = uuid.UUID(user_id_str)
        org_id = uuid.UUID(org_id_str)
    except ValueError:
        raise credentials_exception from None

    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(user_id)

    if user is None:
        raise credentials_exception

    # Validate org membership via OrgToUser
    result = await db.execute(
        select(OrgToUser).where(
            OrgToUser.user_id == user_id,
            OrgToUser.org_id == org_id,
        )
    )
    membership = result.scalar_one_or_none()
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not a member of this organization",
        )

    # Set transient org context on the user instance
    user.org_id = membership.org_id  # type: ignore[attr-defined]
    user.role = membership.role  # type: ignore[attr-defined]
    user.role_id = membership.role_id  # type: ignore[attr-defined]
    user.role_ref = membership.role_ref  # type: ignore[attr-defined]

    # Block API access when password change is required
    if user.must_change_password:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Password change required",
        )

    return user


async def get_current_user_pending_password(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Like get_current_user but allows users with must_change_password=True.

    Used exclusively by the change-password endpoint.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    payload = verify_token(token)
    if payload is None:
        raise credentials_exception

    user_id_str: str | None = payload.get("sub")
    org_id_str: str | None = payload.get("org_id")
    if user_id_str is None or org_id_str is None:
        raise credentials_exception

    try:
        user_id = uuid.UUID(user_id_str)
        org_id = uuid.UUID(org_id_str)
    except ValueError:
        raise credentials_exception from None

    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(user_id)

    if user is None:
        raise credentials_exception

    result = await db.execute(
        select(OrgToUser).where(
            OrgToUser.user_id == user_id,
            OrgToUser.org_id == org_id,
        )
    )
    membership = result.scalar_one_or_none()
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not a member of this organization",
        )

    user.org_id = membership.org_id  # type: ignore[attr-defined]
    user.role = membership.role  # type: ignore[attr-defined]
    user.role_id = membership.role_id  # type: ignore[attr-defined]
    user.role_ref = membership.role_ref  # type: ignore[attr-defined]

    return user


async def get_user_permissions(user: User, db: AsyncSession) -> set[str]:
    """Return the set of permission resource_id strings for a user's role.

    Looks up permissions via the role_id FK first.  When role_id is NULL
    (legacy users created before the RBAC roles table), falls back to the
    default permission set for the user's role enum from permissions.py.

    Args:
        user: The user whose permissions to look up.
        db: The async database session.

    Returns:
        A set of resource_id strings (e.g. {"backlog:view", "backlog:create"}).
    """
    role_id = getattr(user, "role_id", None)
    if role_id is not None:
        perm_repo = PermissionRepository(db)
        return await perm_repo.get_user_permission_ids(role_id)

    # Fallback: derive permissions from the legacy role enum when role_id
    # is NULL (users created before the RBAC roles table was seeded).
    role_enum = getattr(user, "role", None)
    if role_enum is not None:
        from app.core.permissions import DEFAULT_SYSTEM_ROLES

        role_name = str(role_enum)
        for role_def in DEFAULT_SYSTEM_ROLES:
            if role_def.name == role_name:
                logger.info(
                    "permissions_from_role_enum_fallback",
                    user_id=str(user.id),
                    role=role_name,
                )
                return set(role_def.permission_ids)

    logger.warning("no_permissions_resolved", user_id=str(user.id))
    return set()


def require_permissions(
    *permissions: str,
    mode: Literal["all", "any"] = "all",
) -> Callable:
    """FastAPI dependency factory that enforces permission checks.

    Usage::

        @router.get("/", dependencies=[Depends(require_permissions("backlog:view"))])
        @router.post("/approve", dependencies=[Depends(require_permissions("backlog:approve"))])

    Args:
        permissions: One or more permission resource_ids to require.
        mode: "all" requires every listed permission; "any" requires at least one.

    Returns:
        A FastAPI-compatible async dependency function.
    """

    async def _check(
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        # org_owner bypasses all permission checks (enum check first for
        # legacy users without role_id, then DB lookup as defense-in-depth
        # in case the enum attribute is missing but the role row exists).
        role_enum = getattr(current_user, "role", None)
        if role_enum == UserRole.ORG_OWNER:
            return current_user

        role_id = getattr(current_user, "role_id", None)
        if role_id is not None:
            role_repo = RoleRepository(db)
            role_name = await role_repo.get_role_name(role_id)
            if role_name == "org_owner":
                return current_user

        user_perms = await get_user_permissions(current_user, db)
        required = set(permissions)

        if mode == "all":
            if not required.issubset(user_perms):
                missing = required - user_perms
                logger.warning(
                    "permission_denied",
                    user_id=str(current_user.id),
                    missing=sorted(missing),
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Insufficient permissions.",
                )
        else:  # mode == "any"
            if not required.intersection(user_perms):
                logger.warning(
                    "permission_denied",
                    user_id=str(current_user.id),
                    required=sorted(required),
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Insufficient permissions.",
                )

        return current_user

    return _check
