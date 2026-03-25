"""Organization management endpoints."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.organization import Organization
from app.models.user import User
from app.repositories.organization import OrganizationRepository
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
    org_repo = OrganizationRepository(db)
    org = await org_repo.get_by_id(current_user.org_id)
    return [org] if org else []


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
    org_repo = OrganizationRepository(db)
    if await org_repo.get_by_slug(body.slug) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Organization slug already exists",
        )

    org = Organization(
        name=body.name,
        slug=body.slug,
        config=body.config,
    )
    created_org = await org_repo.create(org)

    # Seed agent skills and stage mappings for the new org
    from app.services.bud_stage_seeder import seed_stage_mappings_for_org
    from app.services.skill_loader import seed_skills_for_org

    await seed_skills_for_org(created_org.id, db)
    await seed_stage_mappings_for_org(created_org.id, db)

    return created_org


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
    org_repo = OrganizationRepository(db)
    org = await org_repo.get_by_id(org_id)
    if org is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )
    return org
