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
from app.models.permission import Permission, Role, RolePermission
from app.models.user import User

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

    Args:
        token: The JWT bearer token extracted from the Authorization header.
        db: The async database session.

    Returns:
        The authenticated User ORM instance.

    Raises:
        HTTPException: If the token is invalid or the user does not exist.
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
    if user_id_str is None:
        raise credentials_exception

    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError:
        raise credentials_exception from None

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise credentials_exception

    return user


async def get_user_permissions(user: User, db: AsyncSession) -> set[str]:
    """Return the set of permission resource_id strings for a user's role.

    Args:
        user: The user whose permissions to look up.
        db: The async database session.

    Returns:
        A set of resource_id strings (e.g. {"backlog:view", "backlog:create"}).
    """
    if user.role_id is None:
        return set()

    result = await db.execute(
        select(Permission.resource_id)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .where(RolePermission.role_id == user.role_id)
    )
    return set(result.scalars().all())


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
        if current_user.role_id is not None:
            role_result = await db.execute(
                select(Role.name).where(Role.id == current_user.role_id)
            )
            role_name = role_result.scalar_one_or_none()
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
