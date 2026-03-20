"""Permission, Role, and RBAC models for granular access control."""

import uuid
from enum import StrEnum

from sqlalchemy import Boolean, Enum, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class RoleScopeType(StrEnum):
    """Whether a role is a built-in system role or a custom org-level role."""

    SYSTEM = "system"
    CUSTOM = "custom"


class PermissionCategory(BaseModel):
    """Groups permissions for UI display (e.g. 'Backlog', 'Agents')."""

    __tablename__ = "permission_categories"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    key: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    permissions: Mapped[list["Permission"]] = relationship(
        "Permission", back_populates="category", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<PermissionCategory(key={self.key!r})>"


class Permission(BaseModel):
    """Individual permission with a unique resource_id (e.g. 'backlog:view')."""

    __tablename__ = "permissions"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("permission_categories.id"), nullable=False
    )
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    category: Mapped["PermissionCategory"] = relationship(
        "PermissionCategory", back_populates="permissions", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<Permission(resource_id={self.resource_id!r})>"


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
