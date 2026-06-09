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

"""Team data access — CRUD plus the assignment-filter query.

The headline query is :meth:`TeamRepository.list_member_ids_for_repos`,
which the BUD auto-assigner uses to filter its role-eligible candidate
pool down to members of teams that own any of the BUD's impacted
repos. All other methods support the Settings → Teams CRUD UI.
"""

import uuid
from collections.abc import Sequence
from typing import Final

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.team import Team, TeamMember, TeamRepo, TeamStatus
from app.repositories.base import BaseRepository, rowcount


class _Unset:
    """Singleton sentinel for ``update_team`` to distinguish "skip" vs "set to None"."""

    _instance: "_Unset | None" = None

    def __new__(cls) -> "_Unset":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:  # pragma: no cover — debug only
        return "<UNSET>"


UNSET: Final = _Unset()


class TeamRepository(BaseRepository[Team]):
    """Repository for Team and its membership / repo-ownership joins."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID | None = None) -> None:
        super().__init__(Team, db, org_id=org_id)

    # ------------------------------------------------------------------
    # Team CRUD
    # ------------------------------------------------------------------
    async def list_active(self) -> list[Team]:
        """All active teams in the org, ordered by name."""
        stmt = self._scoped(select(Team).where(Team.status == TeamStatus.ACTIVE)).order_by(
            Team.name
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def list_all_ordered(self) -> list[Team]:
        """All teams including archived, ordered by name."""
        stmt = self._scoped(select(Team)).order_by(Team.name)
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def get_by_name(self, name: str) -> Team | None:
        """Look up a team by name within the org."""
        stmt = self._scoped(select(Team).where(Team.name == name))
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def create_team(self, *, name: str, description: str | None = None) -> Team:
        """Create a new ACTIVE team in the repository's org.

        ``org_id`` is taken from the repository scope — never accept an
        ``org_id`` argument from the caller, which would let a handler
        accidentally create a team in another tenant.
        """
        if self._org_id is None:
            raise ValueError("TeamRepository.create_team requires an org_id scope")
        team = Team(
            org_id=self._org_id,
            name=name,
            description=description,
            status=TeamStatus.ACTIVE,
        )
        self._db.add(team)
        await self._db.flush()
        await self._db.refresh(team)
        return team

    async def update_team(
        self,
        team: Team,
        *,
        name: str | None = None,
        description: str | None | _Unset = UNSET,
        status: TeamStatus | None = None,
    ) -> Team:
        """Mutate the supplied team in-place.

        ``None`` on ``name`` / ``status`` skips that field. ``description``
        uses the ``UNSET`` sentinel so callers can explicitly pass ``None``
        to clear a previously-set description — otherwise a future PATCH
        handler would be forced to write SQL outside this repository to
        null the column, which violates the repo-only rule.
        """
        if name is not None:
            team.name = name
        if not isinstance(description, _Unset):
            team.description = description
        if status is not None:
            team.status = status
        await self._db.flush()
        await self._db.refresh(team)
        return team

    # ------------------------------------------------------------------
    # Members
    # ------------------------------------------------------------------
    async def add_member(self, team: Team, user_id: uuid.UUID) -> TeamMember:
        """Add a user to ``team``.

        The composite FK back to ``org_to_user(user_id, org_id)`` makes
        this raise IntegrityError if the user is not in the team's org
        — that's the cross-tenant safety net.
        """
        member = TeamMember(team_id=team.id, user_id=user_id, org_id=team.org_id)
        self._db.add(member)
        await self._db.flush()
        return member

    async def remove_member(self, team_id: uuid.UUID, user_id: uuid.UUID) -> int:
        """Remove a user from a team. Returns rows deleted (0 or 1).

        Scoped to the repo's ``org_id`` so a leaked team_id from another
        tenant can't delete cross-org rows.
        """
        if self._org_id is None:
            raise ValueError("TeamRepository.remove_member requires an org_id scope")
        result = await self._db.execute(
            delete(TeamMember).where(
                TeamMember.team_id == team_id,
                TeamMember.user_id == user_id,
                TeamMember.org_id == self._org_id,
            )
        )
        return rowcount(result)

    # ------------------------------------------------------------------
    # Repos
    # ------------------------------------------------------------------
    async def add_repo(self, team: Team, repo_id: uuid.UUID) -> TeamRepo:
        """Map a tracked repo to ``team``.

        Same composite-FK safety as ``add_member`` — the repo must
        belong to the team's org or the INSERT fails.
        """
        mapping = TeamRepo(team_id=team.id, repo_id=repo_id, org_id=team.org_id)
        self._db.add(mapping)
        await self._db.flush()
        return mapping

    async def remove_repo(self, team_id: uuid.UUID, repo_id: uuid.UUID) -> int:
        """Unmap a repo from a team. Returns rows deleted (0 or 1)."""
        if self._org_id is None:
            raise ValueError("TeamRepository.remove_repo requires an org_id scope")
        result = await self._db.execute(
            delete(TeamRepo).where(
                TeamRepo.team_id == team_id,
                TeamRepo.repo_id == repo_id,
                TeamRepo.org_id == self._org_id,
            )
        )
        return rowcount(result)

    # ------------------------------------------------------------------
    # Assignment-filter queries (the hot path)
    # ------------------------------------------------------------------
    async def list_member_ids_for_repos(self, repo_ids: Sequence[uuid.UUID]) -> set[uuid.UUID]:
        """User-id set: members of any ACTIVE team owning any of ``repo_ids``.

        The auto-assigner intersects this set with its role-eligible
        candidates so only users in a team owning an impacted repo can
        be picked. Empty ``repo_ids`` returns an empty set without a
        query — that way the caller knows to fall back to org-wide
        candidates rather than treating "no impacted repos" as "no
        candidates exist".

        Tenant scoping happens via ``Team.org_id`` in the JOIN
        predicate — both sides of the join always share the team's
        ``org_id`` thanks to the composite FKs on the join tables.
        """
        if self._org_id is None:
            raise ValueError("TeamRepository.list_member_ids_for_repos requires an org_id scope")
        if not repo_ids:
            return set()
        stmt = (
            select(TeamMember.user_id)
            .distinct()
            .join(TeamRepo, TeamRepo.team_id == TeamMember.team_id)
            .join(Team, Team.id == TeamMember.team_id)
            .where(
                Team.org_id == self._org_id,
                Team.status == TeamStatus.ACTIVE,
                TeamRepo.repo_id.in_(repo_ids),
            )
        )
        result = await self._db.execute(stmt)
        return set(result.scalars().all())

    async def list_developer_pool_for_repo(self, repo_id: uuid.UUID) -> set[uuid.UUID]:
        """User-id set: members of any ACTIVE team owning ``repo_id``.

        Per-repo variant used when assigning TODOs to one specific
        repo's owning team — the caller still picks among returned
        users by role via ``UserRepository.list_active_with_role``.
        """
        return await self.list_member_ids_for_repos([repo_id])

    async def list_teams_for_user(self, user_id: uuid.UUID) -> list[Team]:
        """All ACTIVE teams a user belongs to in this org."""
        if self._org_id is None:
            raise ValueError("TeamRepository.list_teams_for_user requires an org_id scope")
        stmt = (
            select(Team)
            .join(TeamMember, TeamMember.team_id == Team.id)
            .where(
                Team.org_id == self._org_id,
                Team.status == TeamStatus.ACTIVE,
                TeamMember.user_id == user_id,
            )
            .order_by(Team.name)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def list_teams_for_users(
        self, user_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, list[Team]]:
        """Bulk variant for BUD-list rendering. Returns a fresh dict.

        Done in a single query and grouped in Python so the frontend
        can show team badges next to every assignee without N+1.
        """
        if self._org_id is None:
            raise ValueError("TeamRepository.list_teams_for_users requires an org_id scope")
        if not user_ids:
            return {}
        stmt = (
            select(TeamMember.user_id, Team)
            .join(Team, Team.id == TeamMember.team_id)
            .where(
                Team.org_id == self._org_id,
                Team.status == TeamStatus.ACTIVE,
                TeamMember.user_id.in_(user_ids),
            )
            .order_by(Team.name)
        )
        out: dict[uuid.UUID, list[Team]] = {}
        for row in (await self._db.execute(stmt)).all():
            out.setdefault(row.user_id, []).append(row.Team)
        return out

    async def list_teams_for_repo(self, repo_id: uuid.UUID) -> list[Team]:
        """All ACTIVE teams owning ``repo_id`` in this org."""
        if self._org_id is None:
            raise ValueError("TeamRepository.list_teams_for_repo requires an org_id scope")
        stmt = (
            select(Team)
            .join(TeamRepo, TeamRepo.team_id == Team.id)
            .where(
                Team.org_id == self._org_id,
                Team.status == TeamStatus.ACTIVE,
                TeamRepo.repo_id == repo_id,
            )
            .order_by(Team.name)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())
