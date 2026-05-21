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

"""User and organization membership models."""

import uuid
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Enum, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.role import Role


class UserRole(StrEnum):
    """Roles a user can hold within an organization."""

    ORG_OWNER = "org_owner"
    ADMIN = "admin"
    PM = "pm"
    TECH_LEAD = "tech_lead"
    DEVELOPER = "developer"
    DESIGNER = "designer"
    QA = "qa"
    MANAGER = "manager"
    SUPPORT = "support"
    VIEWER = "viewer"


class User(BaseModel):
    """Application user — org membership is tracked via OrgToUser."""

    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("email", name="uq_users_email"),
        # Partial unique index — defence-in-depth for restored DBs
        # where ``uq_users_email`` never landed (the legacy state
        # that allowed duplicate ``users.email`` rows). Migration
        # ``6e375ee9d275`` creates it; declaring it on the model
        # keeps the autogen drift check happy.
        Index(
            "uq_users_email_active",
            "email",
            unique=True,
            postgresql_where="is_active = true",
        ),
    )

    email: Mapped[str] = mapped_column(String(320), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    must_change_password: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    slack_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    github_username: Mapped[str | None] = mapped_column(String(100), nullable=True)
    character_model: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # org_id, role, role_id, role_ref are NOT columns.
    # They are set as transient instance attributes by get_current_user
    # from the OrgToUser membership validated via JWT org_id.
    if TYPE_CHECKING:
        org_id: uuid.UUID
        role: UserRole
        role_id: uuid.UUID | None
        role_ref: "Role | None"

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email!r})>"


class UserEmailAlias(BaseModel):
    """Alternate email addresses for a user (e.g., personal, GitHub noreply).

    During git scans, commits authored with any alias email are attributed
    to the primary user.
    """

    __tablename__ = "user_email_aliases"
    __table_args__ = (UniqueConstraint("org_id", "email", name="uq_alias_org_email"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)

    def __repr__(self) -> str:
        return f"<UserEmailAlias(user_id={self.user_id}, email={self.email!r})>"


class OrgToUser(BaseModel):
    """Tracks membership and per-org role for users in organizations."""

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
    role_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roles.id"), nullable=True
    )

    # Relationships
    role_ref: Mapped["Role | None"] = relationship("Role", lazy="selectin")

    def __repr__(self) -> str:
        return f"<OrgToUser(user_id={self.user_id}, org_id={self.org_id})>"
