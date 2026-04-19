# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Role and RolePermission data access repository."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.permission import Permission, Role, RolePermission
from app.repositories.base import BaseRepository


class RoleRepository(BaseRepository[Role]):
    """Repository for Role queries and role-permission management."""

    def __init__(self, db: AsyncSession) -> None:
        """Initialize the repository.

        Args:
            db: Async SQLAlchemy session.
        """
        super().__init__(Role, db)

    async def list_active(self) -> list[Role]:
        """List all active roles ordered by name.

        Returns:
            List of active Role instances sorted alphabetically by name.
        """
        result = await self._db.execute(
            select(Role).where(Role.is_active.is_(True)).order_by(Role.name)
        )
        return list(result.scalars().all())

    async def get_by_name_system(self, name: str) -> Role | None:
        """Fetch a system role by name (org_id IS NULL).

        Args:
            name: The role name to search for.

        Returns:
            The matching system Role or None.
        """
        result = await self._db.execute(
            select(Role).where(Role.name == name, Role.org_id.is_(None))
        )
        return result.scalar_one_or_none()

    async def get_role_name(self, role_id: uuid.UUID) -> str | None:
        """Fetch just the role name by ID (for permission bypass checks).

        Args:
            role_id: The role UUID.

        Returns:
            The role name string or None if not found.
        """
        result = await self._db.execute(select(Role.name).where(Role.id == role_id))
        return result.scalar_one_or_none()

    async def replace_permissions(
        self,
        role_id: uuid.UUID,
        permission_ids: list[uuid.UUID],
    ) -> None:
        """Replace all permissions for a role.

        Deletes existing role-permission mappings and creates new ones.
        Validates that each permission_id exists.

        Args:
            role_id: The role to update.
            permission_ids: New permission UUIDs to assign.

        Raises:
            ValueError: If any permission_id does not exist.
        """
        # Delete existing mappings
        existing_result = await self._db.execute(
            select(RolePermission).where(RolePermission.role_id == role_id)
        )
        for rp in existing_result.scalars().all():
            await self._db.delete(rp)
        await self._db.flush()

        # Add new mappings (validate each permission exists)
        for perm_id in permission_ids:
            perm_result = await self._db.execute(
                select(Permission).where(Permission.id == perm_id)
            )
            if perm_result.scalar_one_or_none() is None:
                msg = f"Permission {perm_id} not found"
                raise ValueError(msg)
            self._db.add(RolePermission(role_id=role_id, permission_id=perm_id))

        await self._db.flush()

    async def get_existing_permission_ids(self, role_id: uuid.UUID) -> set[uuid.UUID]:
        """Get the set of permission IDs currently assigned to a role.

        Args:
            role_id: The role UUID.

        Returns:
            Set of permission UUIDs assigned to the role.
        """
        result = await self._db.execute(
            select(RolePermission.permission_id).where(RolePermission.role_id == role_id)
        )
        return set(result.scalars().all())
