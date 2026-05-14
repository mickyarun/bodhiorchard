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

"""Role and RolePermission data access repository."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, selectinload

from app.models.permission import Permission
from app.models.role import Role, RolePermission, RoleScopeType
from app.repositories.base import BaseRepository
from app.schemas.permission import PermissionRead
from app.schemas.role import RoleRead

# Tuple shape returned by ``list_orphan_custom_roles`` — kept narrow so
# callers don't need to load the full ORM object just to log a warning.
OrphanCustomRoleRow = tuple[uuid.UUID, str, uuid.UUID | None]


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

    async def read(self, role_id: uuid.UUID) -> RoleRead | None:
        """Return a fully-built :class:`RoleRead` or ``None`` if not found.

        Single source of truth for the role read-shape. Two plain SELECTs
        — no self-referential ORM relationship, no lazy loading, can't
        MissingGreenlet:

        1. Role columns + ``base_role.name`` via a LEFT JOIN to itself.
        2. Attached permissions with their category eager-loaded (the
           ``PermissionRead.category_key`` field needs it).
        """
        base = aliased(Role)
        stmt = (
            select(Role, base.name)
            .outerjoin(base, base.id == Role.base_role_id)
            .where(Role.id == role_id)
        )
        row = (await self._db.execute(stmt)).one_or_none()
        if row is None:
            return None
        role, base_name = row

        perm_stmt = (
            select(Permission)
            .options(selectinload(Permission.category))
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .where(RolePermission.role_id == role_id)
            .order_by(Permission.display_order)
        )
        permissions = (await self._db.execute(perm_stmt)).scalars().all()

        return RoleRead(
            id=role.id,
            name=role.name,
            description=role.description,
            scope_type=role.scope_type.value,
            is_active=role.is_active,
            base_role_id=role.base_role_id,
            base_role_name=base_name,
            permissions=[
                PermissionRead(
                    id=p.id,
                    name=p.name,
                    resource_id=p.resource_id,
                    description=p.description,
                    category_key=p.category.key,
                    display_order=p.display_order,
                )
                for p in permissions
            ],
        )

    async def read_active(self) -> list[RoleRead]:
        """All active roles as :class:`RoleRead` DTOs, ordered by name."""
        result = await self._db.execute(
            select(Role.id).where(Role.is_active.is_(True)).order_by(Role.name)
        )
        ids = list(result.scalars().all())
        out: list[RoleRead] = []
        for rid in ids:
            dto = await self.read(rid)
            if dto is not None:
                out.append(dto)
        return out

    async def list_orphan_custom_roles(self) -> list[OrphanCustomRoleRow]:
        """Return active CUSTOM roles whose ``base_role_id`` is NULL.

        These rows are invisible to ``UserRepository.list_active_with_role``
        because the phase auto-assigner joins through ``base_role_id``.
        The startup seeder logs one warning per row so an admin knows to
        re-edit each role through MembersView.
        """
        stmt = select(Role.id, Role.name, Role.org_id).where(
            Role.scope_type == RoleScopeType.CUSTOM,
            Role.base_role_id.is_(None),
            Role.is_active.is_(True),
        )
        result = await self._db.execute(stmt)
        return [(row[0], row[1], row[2]) for row in result.all()]

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
