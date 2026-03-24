"""FastAPI dependency injection providers."""

import uuid
from collections.abc import AsyncGenerator, Callable
from typing import Literal

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_token
from app.database import AsyncSessionLocal
from app.models.user import OrgToUser, User
from app.repositories.permission import PermissionRepository
from app.repositories.role import RoleRepository
from app.repositories.user import UserRepository

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

    return user


async def get_user_permissions(user: User, db: AsyncSession) -> set[str]:
    """Return the set of permission resource_id strings for a user's role.

    Args:
        user: The user whose permissions to look up.
        db: The async database session.

    Returns:
        A set of resource_id strings (e.g. {"backlog:view", "backlog:create"}).
    """
    role_id = getattr(user, "role_id", None)
    if role_id is None:
        return set()

    perm_repo = PermissionRepository(db)
    return await perm_repo.get_user_permission_ids(role_id)


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
        # org_owner bypasses all permission checks
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
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Missing permissions: {', '.join(sorted(missing))}",
                )
        else:  # mode == "any"
            if not required.intersection(user_perms):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Requires at least one of: {', '.join(sorted(required))}",
                )

        return current_user

    return _check
