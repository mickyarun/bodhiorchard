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

"""Role models — system roles and per-org custom roles.

Permission and PermissionCategory live in :mod:`app.models.permission`.
The Role concept (a name + scope + permissions + inheritance) is its
own first-class entity here.
"""

import uuid
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel
from app.models.permission import Permission


class RoleScopeType(StrEnum):
    """Whether a role is a built-in system role or a custom org-level role."""

    SYSTEM = "system"
    CUSTOM = "custom"


class Role(BaseModel):
    """Role definition — system-wide or per-org custom."""

    __tablename__ = "roles"
    __table_args__ = (UniqueConstraint("name", "org_id", name="uq_roles_name_org"),)

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    org_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=True
    )
    scope_type: Mapped[RoleScopeType] = mapped_column(
        Enum(
            RoleScopeType,
            name="role_scope_type",
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=False,
        default=RoleScopeType.SYSTEM,
    )
    # FK to the seeded SYSTEM role this custom role inherits from.
    # ``None`` for system roles themselves (their ``name`` is the
    # canonical identity). Custom roles MUST set this — phase
    # auto-assignment joins through it to resolve the inherited
    # UserRole. Using an FK (rather than a duplicated enum value) keeps
    # the inheritance relational: rename the system role and every
    # custom child follows automatically.
    #
    # No SQLAlchemy ``relationship()`` on top: self-referential async
    # lazy/selectin loaders triggered MissingGreenlet on freshly-inserted
    # rows in this codebase. Callers that need the inherited role's name
    # join through ``RoleRepository.read`` — a plain SELECT that can't
    # lazy-load.
    #
    # ``index=True`` keeps the model in sync with the migration's
    # ``ix_roles_base_role_id`` so the next ``alembic revision
    # --autogenerate`` produces a noop diff.
    base_role_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("roles.id"),
        nullable=True,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    role_permissions: Mapped[list["RolePermission"]] = relationship(
        "RolePermission", back_populates="role", lazy="selectin", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Role(name={self.name!r}, scope={self.scope_type.value})>"


class RolePermission(BaseModel):
    """Join table linking roles to permissions."""

    __tablename__ = "role_permissions"
    __table_args__ = (
        UniqueConstraint("role_id", "permission_id", name="uq_role_permissions_role_perm"),
        Index("ix_role_perms_role_id", "role_id"),
    )

    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), nullable=False
    )
    permission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("permissions.id", ondelete="CASCADE"), nullable=False
    )

    role: Mapped["Role"] = relationship("Role", back_populates="role_permissions")
    permission: Mapped["Permission"] = relationship("Permission", lazy="selectin")

    def __repr__(self) -> str:
        return f"<RolePermission(role_id={self.role_id}, permission_id={self.permission_id})>"
