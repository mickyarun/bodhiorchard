"""Organization management endpoints."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.organization import Organization
from app.models.user import User
from app.schemas.organization import OrganizationCreate, OrganizationRead

router = APIRouter(tags=["organizations"])


@router.get("/", response_model=list[OrganizationRead])
async def list_organizations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Organization]:
    """List organizations the current user has access to.

    Args:
        current_user: The authenticated user.
        db: The async database session.

    Returns:
        A list of organizations.
    """
    result = await db.execute(select(Organization).where(Organization.id == current_user.org_id))
    return list(result.scalars().all())


@router.post("/", response_model=OrganizationRead, status_code=status.HTTP_201_CREATED)
async def create_organization(
    body: OrganizationCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Organization:
    """Create a new organization.

    Args:
        body: Organization creation data.
        current_user: The authenticated user.
        db: The async database session.

    Returns:
        The newly created Organization.

    Raises:
        HTTPException: If the slug is already taken.
    """
    result = await db.execute(select(Organization).where(Organization.slug == body.slug))
    if result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Organization slug already exists",
        )

    org = Organization(
        name=body.name,
        slug=body.slug,
        config=body.config,
    )
    db.add(org)
    await db.flush()
    await db.refresh(org)

    return org


@router.get("/{org_id}", response_model=OrganizationRead)
async def get_organization(
    org_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Organization:
    """Retrieve a single organization by ID.

    Args:
        org_id: The organization UUID.
        current_user: The authenticated user.
        db: The async database session.

    Returns:
        The requested Organization.

    Raises:
        HTTPException: If the organization is not found.
    """
    result = await db.execute(select(Organization).where(Organization.id == org_id))
    org = result.scalar_one_or_none()
    if org is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )
    return org
