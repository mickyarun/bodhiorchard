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

"""Team service — orchestration + typed exceptions for the Teams REST surface.

Keeps ``api/v1/teams.py`` as thin HTTP plumbing: routes validate
input, call into here, translate domain exceptions to HTTPExceptions.
The service owns:

- ``IntegrityError`` → typed exception translation so handlers never
  catch raw SQLAlchemy errors and so future callers (Slack bot,
  background sync) get the same vocabulary.
- The team-detail projection (multi-repository bulk fetches + sort)
  that would otherwise sprawl across each route.
- The ``description`` ``UNSET`` sentinel plumbing so callers stay
  free of the "did the user mean 'skip' or 'null'?" decision.
"""

import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.team import Team, TeamStatus
from app.repositories.team import UNSET, TeamRepository, _Unset
from app.repositories.tracked_repository import TrackedRepoRepository
from app.repositories.user import UserRepository
from app.schemas.team import TeamMemberRead, TeamRead, TeamRepoRead

__all__ = [
    "MembershipNotFoundError",
    "RepoMappingNotFoundError",
    "TeamError",
    "TeamMembershipConflictError",
    "TeamNameConflictError",
    "TeamNotFoundError",
    "TeamRepoMappingConflictError",
    "add_member",
    "add_repo",
    "archive_team",
    "create_team",
    "get_team_or_raise",
    "list_teams",
    "project_team",
    "remove_member",
    "remove_repo",
    "update_team",
]


# ---------------------------------------------------------------------
# Typed domain exceptions — routes translate each to an HTTPException.
# ---------------------------------------------------------------------


class TeamError(Exception):
    """Base for every domain error raised by the team service."""


class TeamNotFoundError(TeamError):
    """Team id is not in this org."""


class TeamNameConflictError(TeamError):
    """A team with this name already exists in the org."""


class TeamMembershipConflictError(TeamError):
    """Add-member failed: cross-org user OR user already on the team.

    Composite-FK rejection (``fk_team_members_user_org``) and the
    ``uq_team_members_team_user`` unique constraint both surface here
    — both root causes are admin-facing data errors with the same fix
    surface ("either the user isn't in the org or they're already on
    the team"), so a single typed exception keeps the route honest
    without pretending to differentiate.
    """


class TeamRepoMappingConflictError(TeamError):
    """Add-repo failed: cross-org repo OR repo already mapped to the team."""


class MembershipNotFoundError(TeamError):
    """The user is not on the team (or the (team, user) pair never existed)."""


class RepoMappingNotFoundError(TeamError):
    """The repo is not mapped to the team."""


# ---------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------


async def list_teams(db: AsyncSession, org_id: uuid.UUID, *, include_archived: bool) -> list[Team]:
    """List teams in the org. Summary shape — caller projects as needed."""
    repo = TeamRepository(db, org_id=org_id)
    return await (repo.list_all_ordered() if include_archived else repo.list_active())


async def get_team_or_raise(db: AsyncSession, org_id: uuid.UUID, team_id: uuid.UUID) -> Team:
    """Fetch a team within the org or raise :class:`TeamNotFoundError`.

    Tenant-scoped via ``TeamRepository._scoped`` — a leaked team_id
    from another org resolves to ``None`` here, not a 200 with the
    wrong data.
    """
    team = await TeamRepository(db, org_id=org_id).get_by_id(team_id)
    if team is None:
        raise TeamNotFoundError(str(team_id))
    return team


async def project_team(db: AsyncSession, org_id: uuid.UUID, team: Team) -> TeamRead:
    """Hydrate a Team ORM row into a ``TeamRead`` with joined members + repos.

    Two extra bulk queries (users + repos) keep this O(1) regardless
    of member / repo count; rendering happens in Python so a future
    request can swap the projection without touching SQL. Sort order
    is name-stable so a re-render after a no-op PATCH doesn't
    reshuffle the UI.
    """
    user_ids = [m.user_id for m in team.members]
    repo_ids = [r.repo_id for r in team.repos]

    user_triples = await UserRepository(db).list_in_org_by_ids_with_role(org_id, user_ids)
    repos = await TrackedRepoRepository(db, org_id=org_id).list_in_org_by_ids(repo_ids)

    members = [
        TeamMemberRead(
            user_id=u.id,
            name=u.name,
            email=u.email,
            role=eff.value if eff else "viewer",
            role_name=role_name,
            avatar_url=u.avatar_url,
            is_active=u.is_active,
        )
        for (u, eff, role_name) in sorted(user_triples, key=lambda t: t[0].name.lower())
    ]
    repo_reads = [
        TeamRepoRead(
            repo_id=r.id,
            name=r.name,
            path=r.path,
            github_full_name=r.github_repo_full_name,
        )
        for r in sorted(repos, key=lambda r: r.name.lower())
    ]
    return TeamRead(
        id=team.id,
        name=team.name,
        description=team.description,
        status=team.status,
        members=members,
        repos=repo_reads,
    )


# ---------------------------------------------------------------------
# Mutations — pre-check what's cheap, translate FK/UNIQUE violations.
# ---------------------------------------------------------------------


async def create_team(
    db: AsyncSession,
    org_id: uuid.UUID,
    *,
    name: str,
    description: str | None,
) -> Team:
    """Create a team. Raises :class:`TeamNameConflictError` on duplicate."""
    repo = TeamRepository(db, org_id=org_id)
    if await repo.get_by_name(name) is not None:
        raise TeamNameConflictError(name)
    return await repo.create_team(name=name, description=description)


async def update_team(
    db: AsyncSession,
    org_id: uuid.UUID,
    team: Team,
    *,
    name: str | None = None,
    description: str | None | _Unset = UNSET,
    status: TeamStatus | None = None,
) -> Team:
    """Update mutable team fields. Rename collision → :class:`TeamNameConflictError`.

    Pass ``UNSET`` (the default) for ``description`` to skip the field;
    pass ``None`` to clear a previously-set description. Other fields
    use the standard ``None`` = skip convention.
    """
    repo = TeamRepository(db, org_id=org_id)
    try:
        return await repo.update_team(team, name=name, description=description, status=status)
    except IntegrityError as exc:
        raise TeamNameConflictError(name or team.name) from exc


async def archive_team(db: AsyncSession, org_id: uuid.UUID, team: Team) -> Team:
    """Soft-delete by flipping status to ARCHIVED.

    Row is kept so historical timeline events that reference the
    team_id can still resolve a name. Re-activate by passing
    ``status=active`` to :func:`update_team`.
    """
    return await TeamRepository(db, org_id=org_id).update_team(team, status=TeamStatus.ARCHIVED)


async def add_member(db: AsyncSession, org_id: uuid.UUID, team: Team, user_id: uuid.UUID) -> None:
    """Add ``user_id`` to ``team``.

    Composite-FK / unique-constraint violation → :class:`TeamMembershipConflictError`.
    Single exception covers both "not in org" and "already on team" — the
    error detail surface them together because the admin fix is the
    same first step (check the user / check the team's roster).
    """
    try:
        await TeamRepository(db, org_id=org_id).add_member(team, user_id)
    except IntegrityError as exc:
        raise TeamMembershipConflictError(str(user_id)) from exc


async def remove_member(
    db: AsyncSession, org_id: uuid.UUID, team_id: uuid.UUID, user_id: uuid.UUID
) -> None:
    """Remove ``user_id`` from the team. Raises :class:`MembershipNotFoundError` on no-op."""
    deleted = await TeamRepository(db, org_id=org_id).remove_member(team_id, user_id)
    if not deleted:
        raise MembershipNotFoundError(f"{team_id}/{user_id}")


async def add_repo(db: AsyncSession, org_id: uuid.UUID, team: Team, repo_id: uuid.UUID) -> None:
    """Map ``repo_id`` to ``team``. Cross-org / dup → :class:`TeamRepoMappingConflictError`."""
    try:
        await TeamRepository(db, org_id=org_id).add_repo(team, repo_id)
    except IntegrityError as exc:
        raise TeamRepoMappingConflictError(str(repo_id)) from exc


async def remove_repo(
    db: AsyncSession, org_id: uuid.UUID, team_id: uuid.UUID, repo_id: uuid.UUID
) -> None:
    """Unmap ``repo_id`` from the team. Raises :class:`RepoMappingNotFoundError` on no-op."""
    deleted = await TeamRepository(db, org_id=org_id).remove_repo(team_id, repo_id)
    if not deleted:
        raise RepoMappingNotFoundError(f"{team_id}/{repo_id}")
