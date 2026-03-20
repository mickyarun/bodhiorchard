"""Team management endpoints."""

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.team import Team
from app.models.user import User
from app.repositories.organization import OrganizationRepository
from app.repositories.role import RoleRepository
from app.repositories.team import TeamRepository
from app.repositories.user import UserRepository
from app.schemas.teams import (
    AddMemberRequest,
    AssignRoleRequest,
    TeamCreate,
    TeamMemberRead,
    TeamRead,
    TeamUpdate,
)

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["teams"])


def _team_to_read(team: Team) -> TeamRead:
    """Convert a Team model to TeamRead schema.

    Args:
        team: The Team ORM instance.

    Returns:
        TeamRead with members serialized.
    """
    members = [
        TeamMemberRead(
            id=m.id,
            userId=m.user_id,
            userName=m.user.name if m.user else "Unknown",
            email=m.user.email if m.user else "",
            role=m.role,
        )
        for m in (team.members or [])
    ]
    return TeamRead(
        id=team.id,
        name=team.name,
        description=team.description,
        memberCount=len(members),
        createdAt=team.created_at.isoformat() if team.created_at else "",
        members=members,
    )


@router.get("/teams", response_model=list[TeamRead])
async def list_teams(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[TeamRead]:
    """List all teams for the organization.

    Args:
        current_user: The authenticated user.
        db: The async database session.

    Returns:
        List of TeamRead with member details.
    """
    org_repo = OrganizationRepository(db)
    org = await org_repo.get_for_user(current_user)
    team_repo = TeamRepository(db, org_id=org.id)
    teams = await team_repo.list_teams()
    return [_team_to_read(t) for t in teams]


@router.post("/teams", response_model=TeamRead, status_code=status.HTTP_201_CREATED)
async def create_team(
    body: TeamCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TeamRead:
    """Create a new team.

    Args:
        body: Team creation data.
        current_user: The authenticated user.
        db: The async database session.

    Returns:
        The created TeamRead.
    """
    org_repo = OrganizationRepository(db)
    org = await org_repo.get_for_user(current_user)
    team_repo = TeamRepository(db, org_id=org.id)
    team = Team(org_id=org.id, name=body.name, description=body.description)
    await team_repo.add(team)
    await db.flush()
    await db.refresh(team)
    return _team_to_read(team)


@router.get("/teams/{team_id}", response_model=TeamRead)
async def get_team(
    team_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TeamRead:
    """Fetch a single team by ID.

    Args:
        team_id: The team UUID.
        current_user: The authenticated user.
        db: The async database session.

    Returns:
        TeamRead with members.
    """
    org_repo = OrganizationRepository(db)
    org = await org_repo.get_for_user(current_user)
    team_repo = TeamRepository(db, org_id=org.id)
    team = await team_repo.get_with_members(team_id)
    if team is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found.")
    return _team_to_read(team)


@router.patch("/teams/{team_id}", response_model=TeamRead)
async def update_team(
    team_id: uuid.UUID,
    body: TeamUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TeamRead:
    """Update a team's name or description.

    Args:
        team_id: The team UUID.
        body: The update payload.
        current_user: The authenticated user.
        db: The async database session.

    Returns:
        The updated TeamRead.
    """
    org_repo = OrganizationRepository(db)
    org = await org_repo.get_for_user(current_user)
    team_repo = TeamRepository(db, org_id=org.id)
    team = await team_repo.get_with_members(team_id)
    if team is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found.")
    if body.name is not None:
        team.name = body.name
    if body.description is not None:
        team.description = body.description
    await db.flush()
    await db.refresh(team)
    return _team_to_read(team)


@router.delete("/teams/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_team(
    team_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a team and its memberships.

    Args:
        team_id: The team UUID.
        current_user: The authenticated user.
        db: The async database session.
    """
    org_repo = OrganizationRepository(db)
    org = await org_repo.get_for_user(current_user)
    team_repo = TeamRepository(db, org_id=org.id)
    team = await team_repo.get_with_members(team_id)
    if team is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found.")
    await team_repo.delete(team)


@router.post("/teams/{team_id}/members", response_model=TeamMemberRead)
async def add_member(
    team_id: uuid.UUID,
    body: AddMemberRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TeamMemberRead:
    """Add a user to a team.

    Args:
        team_id: The team UUID.
        body: Member data with userId and role.
        current_user: The authenticated user.
        db: The async database session.

    Returns:
        The created TeamMemberRead.
    """
    org_repo = OrganizationRepository(db)
    org = await org_repo.get_for_user(current_user)
    team_repo = TeamRepository(db, org_id=org.id)
    team = await team_repo.get_with_members(team_id)
    if team is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found.")

    user_repo = UserRepository(db, org_id=org.id)
    user = await user_repo.get_by_id(body.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    member = await team_repo.add_member(team_id, body.user_id, body.role)
    return TeamMemberRead(
        id=member.id,
        userId=member.user_id,
        userName=user.name,
        email=user.email,
        role=member.role,
    )


@router.delete("/teams/{team_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    team_id: uuid.UUID,
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Remove a user from a team.

    Args:
        team_id: The team UUID.
        user_id: The user UUID to remove.
        current_user: The authenticated user.
        db: The async database session.
    """
    org_repo = OrganizationRepository(db)
    org = await org_repo.get_for_user(current_user)
    team_repo = TeamRepository(db, org_id=org.id)
    removed = await team_repo.remove_member(team_id, user_id)
    if not removed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found.")


@router.patch("/users/{user_id}/role")
async def assign_role(
    user_id: uuid.UUID,
    body: AssignRoleRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Assign an RBAC role to a user.

    Args:
        user_id: The user UUID.
        body: Role assignment data.
        current_user: The authenticated user.
        db: The async database session.

    Returns:
        Dict confirming the assignment.
    """
    org_repo = OrganizationRepository(db)
    org = await org_repo.get_for_user(current_user)
    user_repo = UserRepository(db, org_id=org.id)
    user = await user_repo.get_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    role_repo = RoleRepository(db)
    role = await role_repo.get_by_id(body.role_id)
    if role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found.")

    user.role_id = body.role_id
    await db.flush()

    return {"userId": str(user_id), "roleId": str(body.role_id), "roleName": role.name}
