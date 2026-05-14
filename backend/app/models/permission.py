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

"""Permission and PermissionCategory models.

The Role concept (and its inheritance via ``base_role_id``, plus the
``RolePermission`` join table) lives in :mod:`app.models.role`. This
module is purely about the catalogue of permissions itself.
"""

import uuid

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


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
