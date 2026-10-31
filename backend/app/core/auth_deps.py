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

"""Authenticated-user dependencies, plus the request DB session from app.database.

Import these through :mod:`app.core.deps`, which is the stable public
surface; this module exists so identity resolution and permission checks
(:mod:`app.core.permission_deps`) can live in separate small files.
"""

import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_token
from app.database import get_db as get_db  # re-exported; one session lifecycle, in app.database
from app.models.user import User, UserRole
from app.repositories.user import UserRepository

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def _credentials_exception() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def _authenticate(token: str, db: AsyncSession) -> User:
    """Resolve the JWT to an active org member with org context attached.

    Sets the transient ``org_id`` / ``role`` / ``role_id`` / ``role_ref``
    attributes on the returned instance (see ``User`` for why they are
    not columns).

    Raises:
        HTTPException: 401 if the token is invalid or the user is missing
            or deactivated; 403 if the user is not a member of the org in
            the token.
    """
    payload = verify_token(token)
    if payload is None:
        raise _credentials_exception()

    user_id_str: str | None = payload.get("sub")
    org_id_str: str | None = payload.get("org_id")
    if user_id_str is None or org_id_str is None:
        raise _credentials_exception()

    try:
        user_id = uuid.UUID(user_id_str)
        org_id = uuid.UUID(org_id_str)
    except ValueError:
        raise _credentials_exception() from None

    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(user_id)

    # Deactivation must end access immediately, not when the token expires.
    if user is None or not user.is_active:
        raise _credentials_exception()

    # Validate org membership + resolve canonical role in one query
    pair = await user_repo.get_membership_with_role(user_id, org_id)
    if pair is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not a member of this organization",
        )
    membership, effective_role = pair

    user.org_id = membership.org_id
    user.role = effective_role or UserRole.DEVELOPER
    user.role_id = membership.role_id
    user.role_ref = membership.role_ref
    return user


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Resolve the current authenticated user from the JWT bearer token.

    Args:
        token: The JWT bearer token extracted from the Authorization header.
        db: The async database session.

    Returns:
        The authenticated User ORM instance with org context set.

    Raises:
        HTTPException: If the token is invalid, the user is missing or
            deactivated, is not a member of the token's org, or must
            change their password first.
    """
    user = await _authenticate(token, db)

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
    return await _authenticate(token, db)
