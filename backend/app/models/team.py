"""Team and team membership models for organizational grouping."""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.user import User


class Team(BaseModel):
    """A named team within an organization."""

    __tablename__ = "teams"
    __table_args__ = (UniqueConstraint("org_id", "name", name="uq_teams_org_name"),)

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    members: Mapped[list["TeamMember"]] = relationship(
        "TeamMember",
        back_populates="team",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Team(id={self.id}, name={self.name!r})>"


class TeamMember(BaseModel):
    """Join table linking users to teams with a role."""

    __tablename__ = "team_members"
    __table_args__ = (UniqueConstraint("team_id", "user_id", name="uq_team_members"),)

    team_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="member")

    team: Mapped["Team"] = relationship("Team", back_populates="members")
    user: Mapped["User"] = relationship("User", lazy="selectin")

    def __repr__(self) -> str:
        return f"<TeamMember(team_id={self.team_id}, user_id={self.user_id})>"
