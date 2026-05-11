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

"""Permission and PermissionCategory data access repository."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.permission import Permission, PermissionCategory, RolePermission
from app.repositories.base import BaseRepository


class PermissionRepository(BaseRepository[Permission]):
    """Repository for Permission and PermissionCategory queries."""

    def __init__(self, db: AsyncSession) -> None:
        """Initialize the repository.

        Args:
            db: Async SQLAlchemy session.
        """
        super().__init__(Permission, db)

    async def get_by_resource_id(self, resource_id: str) -> Permission | None:
        """Fetch a permission by its unique resource_id.

        Args:
            resource_id: The resource identifier (e.g. ``"prds:view"``).

        Returns:
            The matching Permission or None.
        """
        result = await self._db.execute(
            select(Permission).where(Permission.resource_id == resource_id)
        )
        return result.scalar_one_or_none()

    async def get_user_permission_ids(self, role_id: uuid.UUID) -> set[str]:
        """Return the set of permission resource_id strings for a role.

        Args:
            role_id: The role UUID to look up permissions for.

        Returns:
            Set of resource_id strings (e.g. ``{"backlog:view", "prds:edit"}``).
        """
        result = await self._db.execute(
            select(Permission.resource_id)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .where(RolePermission.role_id == role_id)
        )
        return set(result.scalars().all())

    async def list_categories_ordered(self) -> list[PermissionCategory]:
        """List all permission categories ordered by display_order.

        Returns:
            List of PermissionCategory instances sorted by display_order.
        """
        result = await self._db.execute(
            select(PermissionCategory).order_by(PermissionCategory.display_order)
        )
        return list(result.scalars().all())

    async def get_category_by_key(self, key: str) -> PermissionCategory | None:
        """Fetch a permission category by its unique key.

        Args:
            key: The category key string.

        Returns:
            The matching PermissionCategory or None.
        """
        result = await self._db.execute(
            select(PermissionCategory).where(PermissionCategory.key == key)
        )
        return result.scalar_one_or_none()
