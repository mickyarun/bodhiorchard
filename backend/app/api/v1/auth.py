"""Authentication endpoints: login, register, and current user retrieval."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.deps import get_current_user, get_db, get_user_permissions
from app.core.security import create_access_token, hash_password, verify_password
from app.models.organization import Organization
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse
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
    result = await db.execute(select(Organization).where(Organization.slug == body.org_slug))
    org = result.scalar_one_or_none()
    if org is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    # Resolve user
    result = await db.execute(select(User).where(User.org_id == org.id, User.email == body.email))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    token = create_access_token(data={"sub": str(user.id), "org_id": str(org.id)})
    return TokenResponse(
        access_token=token,
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
    result = await db.execute(select(Organization).where(Organization.slug == body.org_slug))
    org = result.scalar_one_or_none()

    if org is None:
        if body.org_name:
            org = Organization(name=body.org_name, slug=body.org_slug)
            db.add(org)
            await db.flush()
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Organization not found. Provide org_name to create one.",
            )

    # Check for duplicate email
    result = await db.execute(select(User).where(User.org_id == org.id, User.email == body.email))
    if result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered in this organization",
        )

    user = User(
        org_id=org.id,
        email=body.email,
        name=body.name,
        password_hash=hash_password(body.password),
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)

    return user


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
        created_at=current_user.created_at,
        updated_at=current_user.updated_at,
    )
