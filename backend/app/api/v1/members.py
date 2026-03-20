"""Organization member listing and role assignment endpoints."""

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.core.security import hash_password
from app.models.user import User
from app.repositories.organization import OrganizationRepository
from app.repositories.role import RoleRepository
from app.repositories.user import UserRepository
from app.schemas.members import AddMemberRequest, AssignRoleRequest, MemberRead

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["members"])


def _user_to_member(user: User) -> MemberRead:
    """Convert a User model to MemberRead schema.

    Args:
        user: The User ORM instance.

    Returns:
        MemberRead with role information.
    """
    role_name: str | None = None
    if user.role_ref:
        role_name = user.role_ref.name
    return MemberRead(
        id=user.id,
        email=user.email,
        name=user.name,
        role=user.role.value,
        roleId=user.role_id,
        roleName=role_name,
        avatarUrl=user.avatar_url,
        githubUsername=user.github_username,
        isActive=user.is_active,
        createdAt=user.created_at.isoformat() if user.created_at else "",
    )


@router.post("/members", response_model=MemberRead, status_code=status.HTTP_201_CREATED)
async def add_member(
    body: AddMemberRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MemberRead:
    """Add a new member to the current user's organization.

    Args:
        body: New member data (email, name, password, optional roleId).
        current_user: The authenticated user.
        db: The async database session.

    Returns:
        The created MemberRead.
    """
    org_repo = OrganizationRepository(db)
    org = await org_repo.get_for_user(current_user)
    user_repo = UserRepository(db, org_id=org.id)

    existing = await user_repo.get_by_email_in_org(org.id, body.email)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered in this organization.",
        )

    if body.role_id:
        role_repo = RoleRepository(db)
        role = await role_repo.get_by_id(body.role_id)
        if role is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found.")

    new_user = User(
        org_id=org.id,
        email=body.email,
        name=body.name,
        password_hash=hash_password(body.password),
        role_id=body.role_id,
        avatar_url=body.avatar_url,
        github_username=body.github_username,
    )
    created = await user_repo.create(new_user)
    await db.refresh(created)

    logger.info(
        "member_added",
        email=body.email,
        added_by=current_user.email,
    )
    return _user_to_member(created)


@router.get("/members", response_model=list[MemberRead])
async def list_members(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[MemberRead]:
    """List all members of the current user's organization.

    Args:
        current_user: The authenticated user.
        db: The async database session.

    Returns:
        List of MemberRead with role details.
    """
    org_repo = OrganizationRepository(db)
    org = await org_repo.get_for_user(current_user)
    user_repo = UserRepository(db, org_id=org.id)
    users = await user_repo.list_by_org(org.id)
    return [_user_to_member(u) for u in users]


@router.patch("/members/{user_id}/role")
async def assign_role(
    user_id: uuid.UUID,
    body: AssignRoleRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MemberRead:
    """Assign an RBAC role to a user.

    Args:
        user_id: The user UUID.
        body: Role assignment data with roleId.
        current_user: The authenticated user.
        db: The async database session.

    Returns:
        Updated MemberRead.
    """
    org_repo = OrganizationRepository(db)
    org = await org_repo.get_for_user(current_user)
    user_repo = UserRepository(db, org_id=org.id)
    user = await user_repo.get_by_id(user_id)
    if user is None or user.org_id != org.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    role_repo = RoleRepository(db)
    role = await role_repo.get_by_id(body.role_id)
    if role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found.")

    user.role_id = body.role_id
    await db.flush()
    await db.refresh(user)

    logger.info(
        "role_assigned",
        user_id=str(user_id),
        role=role.name,
        assigned_by=current_user.email,
    )

    return _user_to_member(user)


@router.patch("/members/{user_id}/status")
async def toggle_member_status(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MemberRead:
    """Toggle a member's active status (soft delete / reactivate).

    Args:
        user_id: The user UUID.
        current_user: The authenticated user.
        db: The async database session.

    Returns:
        Updated MemberRead.
    """
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot deactivate yourself.",
        )

    org_repo = OrganizationRepository(db)
    org = await org_repo.get_for_user(current_user)
    user_repo = UserRepository(db, org_id=org.id)
    user = await user_repo.get_by_id(user_id)
    if user is None or user.org_id != org.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    user.is_active = not user.is_active
    await db.flush()
    await db.refresh(user)

    action = "reactivated" if user.is_active else "deactivated"
    logger.info(
        "member_status_changed", user_id=str(user_id), action=action, by=current_user.email
    )

    return _user_to_member(user)
