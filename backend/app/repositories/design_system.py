# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Design system reference data access repository."""

import uuid
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.design_system import DesignSystemRef
from app.models.tracked_repository import TrackedRepository
from app.repositories.base import BaseRepository


class DesignSystemRefRepository(BaseRepository[DesignSystemRef]):
    """Repository for DesignSystemRef queries, scoped to an organization."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        """Initialize the repository.

        Args:
            db: Async SQLAlchemy session.
            org_id: Organization UUID for scoping queries.
        """
        super().__init__(DesignSystemRef, db, org_id=org_id)

    async def get_default(self) -> DesignSystemRef | None:
        """Return the org-wide default design system (is_default=True).

        Returns:
            The default DesignSystemRef, or None if none set.
        """
        stmt = self._scoped(select(DesignSystemRef).where(DesignSystemRef.is_default.is_(True)))
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_for_repo(self, repo_id: uuid.UUID) -> DesignSystemRef | None:
        """Return the design system for a specific tracked repository.

        Args:
            repo_id: The tracked repository UUID.

        Returns:
            The DesignSystemRef for that repo, or None.
        """
        stmt = self._scoped(select(DesignSystemRef).where(DesignSystemRef.repo_id == repo_id))
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_effective(self, repo_id: uuid.UUID | None) -> DesignSystemRef | None:
        """Return repo-specific design system if exists, else org default.

        Args:
            repo_id: Optional repo UUID. If None, returns the default.

        Returns:
            The most specific DesignSystemRef available, or None.
        """
        if repo_id is not None:
            ds = await self.get_for_repo(repo_id)
            if ds is not None:
                return ds
        return await self.get_default()

    async def upsert(
        self,
        repo_id: uuid.UUID,
        content: str,
        source_hash: str,
        extracted_at: datetime,
        is_default: bool = False,
    ) -> DesignSystemRef:
        """Insert or update a design system for a repo.

        Args:
            repo_id: Tracked repository UUID.
            content: Extracted markdown content.
            source_hash: SHA256 hash of source files for freshness.
            extracted_at: Timestamp of extraction.
            is_default: Whether to mark as org default.

        Returns:
            The created or updated DesignSystemRef.
        """
        existing = await self.get_for_repo(repo_id)
        if existing is not None:
            existing.content = content
            existing.source_hash = source_hash
            existing.extracted_at = extracted_at
            existing.is_default = is_default
            await self._db.flush()
            await self._db.refresh(existing)
            return existing

        ds = DesignSystemRef(
            org_id=self._org_id,
            repo_id=repo_id,
            content=content,
            source_hash=source_hash,
            extracted_at=extracted_at,
            is_default=is_default,
        )
        return await self.create(ds)

    async def set_default(self, design_system_id: uuid.UUID) -> None:
        """Mark one design system as the org default, clearing all others.

        Args:
            design_system_id: The UUID of the design system to make default.
        """
        # Clear is_default on all in this org
        await self._db.execute(
            update(DesignSystemRef)
            .where(DesignSystemRef.org_id == self._org_id)
            .values(is_default=False)
        )
        # Set the target as default
        await self._db.execute(
            update(DesignSystemRef)
            .where(DesignSystemRef.id == design_system_id)
            .values(is_default=True)
        )
        await self._db.flush()

    async def list_with_repo_names(self) -> list[dict]:
        """List all design systems for this org with joined repo names.

        Returns:
            List of dicts with design system fields and repo_name.
        """
        stmt = self._scoped(
            select(DesignSystemRef, TrackedRepository.name.label("repo_name"))
            .join(
                TrackedRepository,
                DesignSystemRef.repo_id == TrackedRepository.id,
                isouter=True,
            )
            .order_by(DesignSystemRef.is_default.desc(), DesignSystemRef.extracted_at.desc())
        )
        result = await self._db.execute(stmt)
        rows = result.all()
        return [
            {
                "id": row.DesignSystemRef.id,
                "org_id": row.DesignSystemRef.org_id,
                "repo_id": row.DesignSystemRef.repo_id,
                "repo_name": row.repo_name,
                "is_default": row.DesignSystemRef.is_default,
                "content": row.DesignSystemRef.content,
                "source_hash": row.DesignSystemRef.source_hash,
                "extracted_at": row.DesignSystemRef.extracted_at,
                "created_at": row.DesignSystemRef.created_at,
                "updated_at": row.DesignSystemRef.updated_at,
            }
            for row in rows
        ]
