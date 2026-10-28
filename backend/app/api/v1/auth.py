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

"""Authentication endpoints: login, token refresh, and current user retrieval.

There is deliberately no self-registration: members join an org only
through an admin invite (``POST /v1/members``) or the setup wizard, so
nobody can add themselves to an org by knowing its slug.
"""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.deps import (
    get_current_user,
    get_current_user_pending_password,
    get_db,
    get_user_permissions,
)
from app.core.security import (
    create_access_token,
    create_refresh_token,
    verify_password,
    verify_token,
)
from app.models.user import User
from app.repositories.organization import OrganizationRepository
from app.repositories.user import UserRepository
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    RefreshRequest,
    TokenResponse,
)
from app.schemas.user import UserRead
from app.services.member_credentials import chose_password, note_own_password

router = APIRouter(tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Authenticate a user and return a JWT access token.

    Args:
        body: Login credentials including email, password, and org slug.
        db: The async database session.

    Returns:
        A TokenResponse containing the access token.

    Raises:
        HTTPException: If credentials are invalid.
    """
    # Resolve organization
    org_repo = OrganizationRepository(db)
    org = await org_repo.get_by_slug(body.org_slug)
    if org is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    # Resolve user
    user_repo = UserRepository(db)
    user = await user_repo.get_by_email_in_org(org.id, body.email)
    # Deactivated accounts get the same generic error as a bad password so
    # the response doesn't confirm which emails exist.
    if (
        user is None
        or not user.is_active
        or not verify_password(body.password, user.password_hash)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    note_own_password(user)
    token_data = {"sub": str(user.id), "org_id": str(org.id)}
    access_token = create_access_token(data=token_data)
    refresh_token = create_refresh_token(data=token_data)
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.auth.access_token_expire_minutes * 60,
        must_change_password=user.must_change_password,
    )


@router.post("/change-password")
async def change_password(
    body: ChangePasswordRequest,
    current_user: User = Depends(get_current_user_pending_password),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Change the current user's password and clear must_change_password flag.

    Args:
        body: New password.
        current_user: The authenticated user.
        db: The async database session.

    Returns:
        Success message.
    """
    chose_password(current_user, body.new_password)
    await db.flush()
    return {"detail": "Password changed successfully."}


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    body: RefreshRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Exchange a valid refresh token for a new access + refresh token pair.

    Args:
        body: The refresh token to validate.
        db: The async database session.

    Returns:
        A new TokenResponse with fresh tokens.

    Raises:
        HTTPException: If the refresh token is invalid or expired.
    """
    payload = verify_token(body.refresh_token, expected_type="refresh")
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    # Verify user still exists and is active
    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(uuid.UUID(user_id))
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    # Someone already signed in before this column existed gets it here.
    note_own_password(user)

    # Preserve org_id from the refresh token (not from User — User has no org_id column)
    org_id = payload.get("org_id")
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token: missing org_id",
        )

    # Validate membership still exists
    if await user_repo.get_membership(user.id, uuid.UUID(org_id)) is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User is no longer a member of this organization",
        )

    token_data = {"sub": str(user.id), "org_id": org_id}
    access_token = create_access_token(data=token_data)
    refresh_token = create_refresh_token(data=token_data)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.auth.access_token_expire_minutes * 60,
    )


@router.get("/me", response_model=UserRead)
async def get_me(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserRead:
    """Return the currently authenticated user's profile with permissions.

    Args:
        current_user: The authenticated user resolved from the JWT token.
        db: The async database session.

    Returns:
        UserRead with role_name and permissions populated.
    """
    perms = await get_user_permissions(current_user, db)
    role_name = current_user.role_ref.name if current_user.role_ref else None

    return UserRead(
        id=current_user.id,
        org_id=current_user.org_id,
        email=current_user.email,
        name=current_user.name,
        role=current_user.role,
        role_name=role_name,
        permissions=sorted(perms),
        slack_id=current_user.slack_id,
        github_username=current_user.github_username,
        character_model=current_user.character_model,
        avatar_url=current_user.avatar_url,
        created_at=current_user.created_at,
        updated_at=current_user.updated_at,
    )
