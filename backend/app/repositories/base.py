# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Generic base repository for async SQLAlchemy 2.0 CRUD operations."""

import uuid
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import BaseModel as ORMBase


class BaseRepository[T: ORMBase]:
    """Async repository base with tenant-scoped CRUD.

    Args:
        model: The SQLAlchemy ORM model class.
        db: An active async database session.
        org_id: Optional tenant UUID. When set, all queries are
            automatically filtered by ``model.org_id == org_id``.
    """

    def __init__(
        self,
        model: type[T],
        db: AsyncSession,
        *,
        org_id: uuid.UUID | None = None,
    ) -> None:
        self._model = model
        self._db = db
        self._org_id = org_id

    def _scoped(self, stmt: Select[tuple[T, ...]]) -> Select[tuple[T, ...]]:
        """Apply tenant scope to a select statement if org_id is set."""
        if self._org_id is not None and hasattr(self._model, "org_id"):
            stmt = stmt.where(self._model.org_id == self._org_id)  # type: ignore[attr-defined]
        return stmt

    async def get_by_id(self, entity_id: uuid.UUID) -> T | None:
        """Fetch a single record by primary key, respecting tenant scope."""
        stmt = self._scoped(select(self._model).where(self._model.id == entity_id))
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_all(
        self,
        *,
        order_by: Any = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[T]:
        """List all records, optionally ordered and paginated."""
        stmt = self._scoped(select(self._model))
        if order_by is not None:
            stmt = stmt.order_by(order_by)
        if limit is not None:
            stmt = stmt.limit(limit)
        if offset is not None:
            stmt = stmt.offset(offset)
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def count(self) -> int:
        """Count records respecting tenant scope."""
        stmt = self._scoped(select(func.count(self._model.id)))
        result = await self._db.execute(stmt)
        return result.scalar() or 0

    async def create(self, entity: T) -> T:
        """Add a new entity, flush, and refresh."""
        self._db.add(entity)
        await self._db.flush()
        await self._db.refresh(entity)
        return entity

    async def add(self, entity: T) -> None:
        """Add without flush (for batch operations)."""
        self._db.add(entity)

    async def flush(self) -> None:
        """Flush pending changes."""
        await self._db.flush()

    async def delete(self, entity: T) -> None:
        """Delete a single entity."""
        await self._db.delete(entity)
        await self._db.flush()
