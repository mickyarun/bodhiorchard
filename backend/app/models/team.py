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

"""Team models — named subsets of org members mapped to one or more repos.

A Team scopes auto-assignment: the BUD lifecycle picker filters its
role-eligible candidate pool down to members of teams that own the
BUD's impacted repos. Roles themselves stay on ``OrgToUser`` — a team
does not override what a user's role is, only which work they're
considered for.

Tenant-safety wiring (both join tables carry ``org_id`` plus composite
FKs so cross-org rows are a DB-level impossibility, not an
application-layer convention):

- ``team_members(team_id, org_id)`` → ``teams(id, org_id)`` — guarantees
  the membership row belongs to the team's own org.
- ``team_members(user_id, org_id)`` → ``org_to_user(user_id, org_id)`` —
  guarantees the user is currently a member of that org; offboarding a
  user via removal from ``org_to_user`` cascades the team rows away.
- ``team_repos(team_id, org_id)`` → ``teams(id, org_id)`` — same team
  tenant alignment as above.
- ``team_repos(repo_id, org_id)`` → ``tracked_repositories(id, org_id)``
  — guarantees the repo is owned by the team's org.
"""

import uuid
from enum import StrEnum

from sqlalchemy import (
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class TeamStatus(StrEnum):
    """Lifecycle status of a Team."""

    ACTIVE = "active"
    ARCHIVED = "archived"


class Team(BaseModel):
    """A named subset of an organization's members, mapped to repos."""

    __tablename__ = "teams"
    __table_args__ = (
        UniqueConstraint("org_id", "name", name="uq_teams_org_name"),
        # ``(id, org_id)`` is the composite-FK target the join tables
        # reference so their ``org_id`` MUST match the team's own org.
        # ``id`` alone is unique (it's the PK), so this constraint adds
        # no real restriction — it only declares the unique index PG
        # needs to accept the composite FK.
        UniqueConstraint("id", "org_id", name="uq_teams_id_org"),
        Index("ix_teams_org_status", "org_id", "status"),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[TeamStatus] = mapped_column(
        Enum(
            TeamStatus,
            name="team_status",
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=False,
        default=TeamStatus.ACTIVE,
    )

    members: Mapped[list["TeamMember"]] = relationship(
        "TeamMember",
        back_populates="team",
        lazy="selectin",
        cascade="all, delete-orphan",
    )
    repos: Mapped[list["TeamRepo"]] = relationship(
        "TeamRepo",
        back_populates="team",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Team(name={self.name!r}, status={self.status.value})>"


class TeamMember(BaseModel):
    """Join row: a user is a member of a team.

    No ``role`` column — the user's effective role is whatever
    ``OrgToUser.role_id`` resolves to in this org. A user can be a
    member of multiple teams; their role applies uniformly.

    ``org_id`` is denormalised so the composite FKs below can enforce
    that the team, the user's org membership, and the row itself all
    point at the same tenant.
    """

    __tablename__ = "team_members"
    __table_args__ = (
        UniqueConstraint("team_id", "user_id", name="uq_team_members_team_user"),
        # Composite FK → ``teams(id, org_id)``: same-org as the team.
        ForeignKeyConstraint(
            ["team_id", "org_id"],
            ["teams.id", "teams.org_id"],
            ondelete="CASCADE",
            name="fk_team_members_team_org",
        ),
        # Composite FK → ``org_to_user(user_id, org_id)``: the user is
        # currently in that org. Offboarding removes the OrgToUser row,
        # which cascades this membership away.
        ForeignKeyConstraint(
            ["user_id", "org_id"],
            ["org_to_user.user_id", "org_to_user.org_id"],
            ondelete="CASCADE",
            name="fk_team_members_user_org",
        ),
        Index("ix_team_members_user_id", "user_id"),
    )

    team_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    team: Mapped["Team"] = relationship("Team", back_populates="members")

    def __repr__(self) -> str:
        return f"<TeamMember(team_id={self.team_id}, user_id={self.user_id})>"


class TeamRepo(BaseModel):
    """Join row: a team owns a tracked repository.

    Many-to-many — a team can own many repos, a repo can be owned by
    many teams. The assignment filter unions all teams owning any of
    a BUD's impacted repos, then intersects with the role pool.

    Carries ``org_id`` for the same tenant-alignment reason as
    ``TeamMember``: composite FKs make cross-org links impossible.
    """

    __tablename__ = "team_repos"
    __table_args__ = (
        UniqueConstraint("team_id", "repo_id", name="uq_team_repos_team_repo"),
        ForeignKeyConstraint(
            ["team_id", "org_id"],
            ["teams.id", "teams.org_id"],
            ondelete="CASCADE",
            name="fk_team_repos_team_org",
        ),
        ForeignKeyConstraint(
            ["repo_id", "org_id"],
            ["tracked_repositories.id", "tracked_repositories.org_id"],
            ondelete="CASCADE",
            name="fk_team_repos_repo_org",
        ),
        Index("ix_team_repos_repo_id", "repo_id"),
    )

    team_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    repo_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    team: Mapped["Team"] = relationship("Team", back_populates="repos")

    def __repr__(self) -> str:
        return f"<TeamRepo(team_id={self.team_id}, repo_id={self.repo_id})>"
