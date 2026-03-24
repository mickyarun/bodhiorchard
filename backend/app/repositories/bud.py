"""BUD document data access repository."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.bud import BUDChatMessage, BUDDesign, BUDDesignStatus, BUDDocument
from app.models.tracked_repository import TrackedRepository
from app.repositories.base import BaseRepository


class BUDRepository(BaseRepository[BUDDocument]):
    """Repository for BUDDocument queries, scoped to an organization."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        """Initialize the repository.

        Args:
            db: Async SQLAlchemy session.
            org_id: Organization UUID for scoping queries.
        """
        super().__init__(BUDDocument, db, org_id=org_id)

    async def list_buds(
        self,
        *,
        status_filter: str | None = None,
        limit: int | None = None,
    ) -> list[BUDDocument]:
        """List BUDs ordered by bud_number descending.

        Args:
            status_filter: Optional status string to filter by.
            limit: Maximum number of results.

        Returns:
            List of BUDDocument instances.
        """
        stmt = self._scoped(select(BUDDocument).order_by(BUDDocument.bud_number.desc()))
        if status_filter:
            stmt = stmt.where(BUDDocument.status == status_filter)
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def get_by_number(self, bud_number: int) -> BUDDocument | None:
        """Fetch a BUD by its number within the organization.

        Args:
            bud_number: The BUD number to look up.

        Returns:
            The BUDDocument, or None if not found.
        """
        stmt = self._scoped(select(BUDDocument).where(BUDDocument.bud_number == bud_number))
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def next_bud_number(self) -> int:
        """Get the next auto-incremented BUD number for the organization.

        Returns:
            The next available BUD number (max + 1, or 1 if none exist).
        """
        result = await self._db.execute(
            select(func.coalesce(func.max(BUDDocument.bud_number), 0)).where(
                BUDDocument.org_id == self._org_id
            )
        )
        return result.scalar_one() + 1


class BUDDesignRepository(BaseRepository[BUDDesign]):
    """Repository for per-repo BUD design wireframes."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        """Initialize with async session and organization scope."""
        super().__init__(BUDDesign, db, org_id=org_id)

    async def list_for_bud(self, bud_id: uuid.UUID) -> list[BUDDesign]:
        """List all designs for a BUD, ordered by creation time."""
        stmt = self._scoped(
            select(BUDDesign).where(BUDDesign.bud_id == bud_id).order_by(BUDDesign.created_at)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def list_with_repo_names(self, bud_id: uuid.UUID) -> list[dict]:
        """List designs for a BUD with joined repo names."""
        stmt = self._scoped(
            select(BUDDesign, TrackedRepository.name.label("repo_name"))
            .join(
                TrackedRepository,
                BUDDesign.repo_id == TrackedRepository.id,
                isouter=True,
            )
            .where(BUDDesign.bud_id == bud_id)
            .order_by(BUDDesign.created_at)
        )
        result = await self._db.execute(stmt)
        rows = result.all()
        return [
            {
                "id": row.BUDDesign.id,
                "bud_id": row.BUDDesign.bud_id,
                "repo_id": row.BUDDesign.repo_id,
                "repo_name": row.repo_name,
                "design_html": row.BUDDesign.design_html,
                "notes": row.BUDDesign.notes,
                "status": row.BUDDesign.status,
                "job_id": row.BUDDesign.job_id,
                "created_at": row.BUDDesign.created_at,
                "updated_at": row.BUDDesign.updated_at,
            }
            for row in rows
        ]

    async def upsert(
        self,
        bud_id: uuid.UUID,
        repo_id: uuid.UUID | None,
        *,
        design_html: str | None = None,
        status: BUDDesignStatus = BUDDesignStatus.PENDING,
        job_id: str | None = None,
    ) -> BUDDesign:
        """Create or update a design for a (bud, repo) pair."""
        stmt = self._scoped(
            select(BUDDesign)
            .where(BUDDesign.bud_id == bud_id)
            .where(
                BUDDesign.repo_id == repo_id
                if repo_id is not None
                else BUDDesign.repo_id.is_(None)
            )
        )
        result = await self._db.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing is not None:
            if design_html is not None:
                existing.design_html = design_html
            existing.status = status
            if job_id is not None:
                existing.job_id = job_id
            await self._db.flush()
            await self._db.refresh(existing)
            return existing

        design = BUDDesign(
            org_id=self._org_id,
            bud_id=bud_id,
            repo_id=repo_id,
            design_html=design_html,
            status=status,
            job_id=job_id,
        )
        return await self.create(design)


class BUDChatMessageRepository(BaseRepository[BUDChatMessage]):
    """Repository for persisted BUD chat messages."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        """Initialize with async session and organization scope."""
        super().__init__(BUDChatMessage, db, org_id=org_id)

    async def list_messages(
        self,
        bud_id: uuid.UUID,
        section: str,
        design_id: uuid.UUID | None = None,
        session_id: uuid.UUID | None = None,
    ) -> list[BUDChatMessage]:
        """List chat messages for a BUD section, optionally scoped to design and session."""
        stmt = self._scoped(
            select(BUDChatMessage)
            .options(joinedload(BUDChatMessage.user))
            .where(BUDChatMessage.bud_id == bud_id)
            .where(BUDChatMessage.section == section)
            .order_by(BUDChatMessage.created_at)
        )
        if design_id is not None:
            stmt = stmt.where(BUDChatMessage.design_id == design_id)
        else:
            stmt = stmt.where(BUDChatMessage.design_id.is_(None))
        if session_id is not None:
            stmt = stmt.where(BUDChatMessage.session_id == session_id)
        else:
            stmt = stmt.where(BUDChatMessage.session_id.is_(None))
        result = await self._db.execute(stmt)
        return list(result.scalars().unique().all())

    async def list_recent_messages(
        self,
        bud_id: uuid.UUID,
        section: str,
        design_id: uuid.UUID | None = None,
        session_id: uuid.UUID | None = None,
        limit: int = 10,
    ) -> list[BUDChatMessage]:
        """Fetch the most recent N messages for LLM context injection.

        Returns messages in chronological order (oldest first).
        """
        stmt = self._scoped(
            select(BUDChatMessage)
            .options(joinedload(BUDChatMessage.user))
            .where(BUDChatMessage.bud_id == bud_id)
            .where(BUDChatMessage.section == section)
            .order_by(BUDChatMessage.created_at.desc())
            .limit(limit)
        )
        if design_id is not None:
            stmt = stmt.where(BUDChatMessage.design_id == design_id)
        else:
            stmt = stmt.where(BUDChatMessage.design_id.is_(None))
        if session_id is not None:
            stmt = stmt.where(BUDChatMessage.session_id == session_id)
        else:
            stmt = stmt.where(BUDChatMessage.session_id.is_(None))
        result = await self._db.execute(stmt)
        msgs = list(result.scalars().unique().all())
        msgs.reverse()  # Chronological order
        return msgs

    async def add_message(
        self,
        bud_id: uuid.UUID,
        section: str,
        role: str,
        message: str,
        design_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
        session_id: uuid.UUID | None = None,
    ) -> BUDChatMessage:
        """Create a new chat message."""
        msg = BUDChatMessage(
            org_id=self._org_id,
            bud_id=bud_id,
            section=section,
            design_id=design_id,
            role=role,
            message=message,
            user_id=user_id,
            session_id=session_id,
        )
        return await self.create(msg)
