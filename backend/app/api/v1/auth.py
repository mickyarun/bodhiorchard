"""Authentication endpoints: login, register, and current user retrieval."""

import uuid

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
    hash_password,
    verify_password,
    verify_token,
)
from app.models.organization import Organization
from app.models.user import OrgToUser, User, UserRole
from app.repositories.organization import OrganizationRepository
from app.repositories.user import UserRepository
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
)
from app.schemas.user import UserRead

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
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

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
) -> dict:
    """Change the current user's password and clear must_change_password flag.

    Args:
        body: New password.
        current_user: The authenticated user.
        db: The async database session.

    Returns:
        Success message.
    """
    current_user.password_hash = hash_password(body.new_password)
    current_user.must_change_password = False
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
    payload = verify_token(body.refresh_token)
    if payload is None or payload.get("type") != "refresh":
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
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    # Preserve org_id from the refresh token (not from User — User has no org_id column)
    org_id = payload.get("org_id")
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token: missing org_id",
        )

    # Validate membership still exists
    from sqlalchemy import select as sa_select

    membership = await db.execute(
        sa_select(OrgToUser).where(
            OrgToUser.user_id == user.id,
            OrgToUser.org_id == uuid.UUID(org_id),
        )
    )
    if membership.scalar_one_or_none() is None:
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


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> User:
    """Register a new user account within an organization.

    Creates the organization if it does not exist and org_name is provided.

    Args:
        body: Registration data including email, password, and org slug.
        db: The async database session.

    Returns:
        The newly created User.

    Raises:
        HTTPException: If the organization is not found or email is taken.
    """
    # Resolve or create organization
    org_repo = OrganizationRepository(db)
    org = await org_repo.get_by_slug(body.org_slug)

    if org is None:
        if body.org_name:
            org = Organization(name=body.org_name, slug=body.org_slug)
            await org_repo.create(org)
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Organization not found. Provide org_name to create one.",
            )

    # Check for duplicate email
    user_repo = UserRepository(db)
    if await user_repo.get_by_email_in_org(org.id, body.email) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered in this organization",
        )

    user = User(
        email=body.email,
        name=body.name,
        password_hash=hash_password(body.password),
    )
    created = await user_repo.create(user)

    # Create org membership
    membership = OrgToUser(user_id=created.id, org_id=org.id, role=UserRole.DEVELOPER)
    db.add(membership)
    await db.flush()

    # Set transient org context for the response serialization
    created.org_id = org.id  # type: ignore[attr-defined]
    created.role = UserRole.DEVELOPER  # type: ignore[attr-defined]
    created.role_id = None  # type: ignore[attr-defined]
    created.role_ref = None  # type: ignore[attr-defined]

    return created


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
        created_at=current_user.created_at,
        updated_at=current_user.updated_at,
    )
