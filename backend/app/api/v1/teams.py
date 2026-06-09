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

"""Teams CRUD endpoints — thin HTTP plumbing over ``services/team_service``.

Every business rule (uniqueness, FK integrity, soft-delete semantics,
member/repo orchestration) lives in the service. The handlers here
just validate input, gate on permissions, call the service, and
translate domain exceptions to HTTPExceptions.
"""

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db, require_permissions
from app.models.user import User
from app.repositories.organization import OrganizationRepository
from app.repositories.team import UNSET
from app.schemas.team import (
    TeamCreate,
    TeamMembershipBody,
    TeamRead,
    TeamRepoBody,
    TeamSummary,
    TeamUpdate,
)
from app.services import team_service
from app.services.team_service import (
    MembershipNotFoundError,
    RepoMappingNotFoundError,
    TeamMembershipConflictError,
    TeamNameConflictError,
    TeamNotFoundError,
    TeamRepoMappingConflictError,
)

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["teams"])


async def _org_id_for(current_user: User, db: AsyncSession) -> uuid.UUID:
    """One-line org-from-user lookup used by every handler."""
    org = await OrganizationRepository(db).get_for_user(current_user)
    return org.id


def _not_found(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


@router.get(
    "/teams",
    response_model=list[TeamSummary],
    dependencies=[Depends(require_permissions("team:view"))],
)
async def list_teams(
    include_archived: bool = False,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[TeamSummary]:
    """List teams in the current org. Summary shape — no joined data."""
    org_id = await _org_id_for(current_user, db)
    teams = await team_service.list_teams(db, org_id, include_archived=include_archived)
    return [TeamSummary.model_validate(t) for t in teams]


@router.post(
    "/teams",
    response_model=TeamRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permissions("team:manage"))],
)
async def create_team(
    body: TeamCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TeamRead:
    """Create a new team."""
    org_id = await _org_id_for(current_user, db)
    try:
        team = await team_service.create_team(
            db, org_id, name=body.name, description=body.description
        )
    except TeamNameConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A team with this name already exists in this organization.",
        ) from exc
    logger.info("team_created", team_id=str(team.id), name=team.name, org_id=str(org_id))
    return await team_service.project_team(db, org_id, team)


@router.get(
    "/teams/{team_id}",
    response_model=TeamRead,
    dependencies=[Depends(require_permissions("team:view"))],
)
async def get_team(
    team_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TeamRead:
    """Get a single team with joined members + repos."""
    org_id = await _org_id_for(current_user, db)
    try:
        team = await team_service.get_team_or_raise(db, org_id, team_id)
    except TeamNotFoundError as exc:
        raise _not_found("Team not found.") from exc
    return await team_service.project_team(db, org_id, team)


@router.patch(
    "/teams/{team_id}",
    response_model=TeamRead,
    dependencies=[Depends(require_permissions("team:manage"))],
)
async def update_team(
    team_id: uuid.UUID,
    body: TeamUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TeamRead:
    """Patch team name / description / status. None on a field skips it.

    ``description`` is the only field that can be explicitly cleared:
    pass ``null`` to clear, omit to preserve the prior value.
    """
    org_id = await _org_id_for(current_user, db)
    try:
        team = await team_service.get_team_or_raise(db, org_id, team_id)
    except TeamNotFoundError as exc:
        raise _not_found("Team not found.") from exc

    # Use the UNSET sentinel so the service can distinguish "omit"
    # from "set to None" without us replicating the logic per call.
    description_arg: str | None | object = (
        body.description if "description" in body.model_fields_set else UNSET
    )

    try:
        updated = await team_service.update_team(
            db,
            org_id,
            team,
            name=body.name,
            description=description_arg,  # type: ignore[arg-type]
            status=body.status,
        )
    except TeamNameConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A team with this name already exists in this organization.",
        ) from exc
    return await team_service.project_team(db, org_id, updated)


@router.delete(
    "/teams/{team_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permissions("team:manage"))],
)
async def archive_team(
    team_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Soft-delete by flipping status to ARCHIVED.

    The row is kept so historical timeline events that reference
    ``team_id`` can still resolve a name. Re-activate by PATCH-ing
    status back to ``active``.
    """
    org_id = await _org_id_for(current_user, db)
    try:
        team = await team_service.get_team_or_raise(db, org_id, team_id)
    except TeamNotFoundError as exc:
        raise _not_found("Team not found.") from exc
    await team_service.archive_team(db, org_id, team)


@router.post(
    "/teams/{team_id}/members",
    response_model=TeamRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permissions("team:manage"))],
)
async def add_team_member(
    team_id: uuid.UUID,
    body: TeamMembershipBody,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TeamRead:
    """Add a user to a team. The composite FK rejects cross-org users."""
    org_id = await _org_id_for(current_user, db)
    try:
        team = await team_service.get_team_or_raise(db, org_id, team_id)
    except TeamNotFoundError as exc:
        raise _not_found("Team not found.") from exc
    try:
        await team_service.add_member(db, org_id, team, body.user_id)
    except TeamMembershipConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is not a member of this organization, or is already on this team.",
        ) from exc
    await db.refresh(team)
    return await team_service.project_team(db, org_id, team)


@router.delete(
    "/teams/{team_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permissions("team:manage"))],
)
async def remove_team_member(
    team_id: uuid.UUID,
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Remove a user from a team."""
    org_id = await _org_id_for(current_user, db)
    try:
        await team_service.get_team_or_raise(db, org_id, team_id)
        await team_service.remove_member(db, org_id, team_id, user_id)
    except TeamNotFoundError as exc:
        raise _not_found("Team not found.") from exc
    except MembershipNotFoundError as exc:
        raise _not_found("User is not on this team.") from exc


@router.post(
    "/teams/{team_id}/repos",
    response_model=TeamRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permissions("team:manage"))],
)
async def add_team_repo(
    team_id: uuid.UUID,
    body: TeamRepoBody,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TeamRead:
    """Map a tracked repo to a team. Composite FK rejects cross-org repos."""
    org_id = await _org_id_for(current_user, db)
    try:
        team = await team_service.get_team_or_raise(db, org_id, team_id)
    except TeamNotFoundError as exc:
        raise _not_found("Team not found.") from exc
    try:
        await team_service.add_repo(db, org_id, team, body.repo_id)
    except TeamRepoMappingConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Repo not found in this organization, or already mapped to this team.",
        ) from exc
    await db.refresh(team)
    return await team_service.project_team(db, org_id, team)


@router.delete(
    "/teams/{team_id}/repos/{repo_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permissions("team:manage"))],
)
async def remove_team_repo(
    team_id: uuid.UUID,
    repo_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Unmap a repo from a team."""
    org_id = await _org_id_for(current_user, db)
    try:
        await team_service.get_team_or_raise(db, org_id, team_id)
        await team_service.remove_repo(db, org_id, team_id, repo_id)
    except TeamNotFoundError as exc:
        raise _not_found("Team not found.") from exc
    except RepoMappingNotFoundError as exc:
        raise _not_found("Repo is not mapped to this team.") from exc
