"""User and organization membership models."""

import uuid
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.organization import Organization
    from app.models.permission import Role


class UserRole(StrEnum):
    """Roles a user can hold within an organization."""

    ORG_OWNER = "org_owner"
    ADMIN = "admin"
    PM = "pm"
    TECH_LEAD = "tech_lead"
    DEVELOPER = "developer"
    DESIGNER = "designer"
    QA = "qa"
    SUPPORT = "support"
    VIEWER = "viewer"


class User(BaseModel):
    """Application user belonging to an organization."""

    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("org_id", "email", name="uq_users_org_email"),)

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role", values_callable=lambda e: [x.value for x in e]),
        nullable=False,
        default=UserRole.DEVELOPER,
    )
    slack_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    github_username: Mapped[str | None] = mapped_column(String(100), nullable=True)
    role_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roles.id"), nullable=True
    )

    # Relationships
    organization: Mapped["Organization"] = relationship(
        "Organization", back_populates="users", lazy="selectin"
    )
    role_ref: Mapped["Role | None"] = relationship("Role", lazy="selectin")

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email!r})>"


class OrgToUser(BaseModel):
    """Tracks membership metadata for users in organizations."""

    __tablename__ = "org_to_user"
    __table_args__ = (UniqueConstraint("user_id", "org_id", name="uq_org_to_user_user_org"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role", values_callable=lambda e: [x.value for x in e]),
        nullable=False,
        default=UserRole.DEVELOPER,
    )

    def __repr__(self) -> str:
        return f"<OrgToUser(user_id={self.user_id}, org_id={self.org_id})>"
