# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""BUD document data access repository."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, lazyload

from app.models.bud import BUDChatMessage, BUDDesign, BUDDesignStatus, BUDDocument, BUDStatus
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

    async def get_by_id_for_update(self, entity_id: uuid.UUID) -> BUDDocument | None:
        """Fetch a BUD with a row-level lock (SELECT ... FOR UPDATE).

        Use when updating JSONB columns that require atomic read-modify-write.
        Disables eager-loaded joins (e.g. assignee) since FOR UPDATE cannot
        be applied to the nullable side of an outer join.
        """
        stmt = self._scoped(
            select(BUDDocument)
            .where(BUDDocument.id == entity_id)
            .options(lazyload(BUDDocument.assignee))
            .with_for_update()
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

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

    async def find_nearest_full_with_distance(
        self, candidate_vector
    ) -> tuple[BUDDocument, float] | None:
        """Nearest full BUDDocument with its cosine distance, or ``None``."""
        stmt = self._scoped(
            select(
                BUDDocument,
                BUDDocument.embedding.cosine_distance(candidate_vector).label("distance"),
            )
            .where(BUDDocument.embedding.is_not(None))
            .order_by("distance")
            .limit(1)
        )
        result = await self._db.execute(stmt)
        row = result.first()
        return (row[0], row[1]) if row else None

    async def find_nearest_neighbor(
        self, candidate_vector, *, exclude_bud_ids: list[uuid.UUID] | None = None
    ) -> tuple[uuid.UUID, int, float] | None:
        """Nearest BUD by pgvector cosine distance.

        Returns ``(bud_id, bud_number, distance)`` or ``None`` if no
        BUDs in the org have an embedding.
        """
        stmt = self._scoped(
            select(
                BUDDocument.id,
                BUDDocument.bud_number,
                BUDDocument.embedding.cosine_distance(candidate_vector).label("distance"),
            )
            .where(BUDDocument.embedding.is_not(None))
            .order_by("distance")
            .limit(1)
        )
        if exclude_bud_ids:
            stmt = stmt.where(BUDDocument.id.not_in(exclude_bud_ids))
        result = await self._db.execute(stmt)
        row = result.first()
        return (row[0], row[1], row[2]) if row else None

    async def count_active_loads_for_assignees(
        self, assignee_ids: list[uuid.UUID], excluded_statuses: list[str]
    ) -> dict[uuid.UUID, int]:
        """Active-BUD count per assignee in ``assignee_ids``."""
        if not assignee_ids:
            return {}
        stmt = self._scoped(
            select(BUDDocument.assignee_id, func.count())
            .where(
                BUDDocument.assignee_id.in_(assignee_ids),
                BUDDocument.status.notin_(excluded_statuses),
            )
            .group_by(BUDDocument.assignee_id)
        )
        result = await self._db.execute(stmt)
        return {row[0]: row[1] for row in result.all()}

    async def count_assignee_workload(
        self,
        assignee_id: uuid.UUID,
        excluded_statuses: list[str],
        *,
        exclude_bud_id: uuid.UUID | None = None,
    ) -> int:
        """Count BUDs assigned to a user, excluding terminal statuses (and optionally
        a specific BUD id).
        """
        stmt = self._scoped(
            select(func.count())
            .select_from(BUDDocument)
            .where(
                BUDDocument.assignee_id == assignee_id,
                BUDDocument.status.notin_(excluded_statuses),
            )
        )
        if exclude_bud_id is not None:
            stmt = stmt.where(BUDDocument.id != exclude_bud_id)
        result = await self._db.execute(stmt)
        return result.scalar_one()

    async def list_recent_completed(self, *, limit: int = 5) -> list[BUDDocument]:
        """Most-recently-updated PROD/CLOSED BUDs that have ``estimated_dates`` set."""
        stmt = self._scoped(
            select(BUDDocument)
            .where(
                BUDDocument.status.in_([BUDStatus.PROD.value, BUDStatus.CLOSED.value]),
                BUDDocument.estimated_dates.is_not(None),
            )
            .order_by(BUDDocument.updated_at.desc())
            .limit(limit)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def list_completed_in_complexity_range(
        self, low: int, high: int, *, limit: int = 50
    ) -> list[BUDDocument]:
        """PROD/CLOSED BUDs whose complexity is in ``[low, high]``."""
        stmt = self._scoped(
            select(BUDDocument)
            .where(
                BUDDocument.status.in_([BUDStatus.PROD.value, BUDStatus.CLOSED.value]),
                BUDDocument.complexity.between(low, high),
                BUDDocument.created_at.is_not(None),
            )
            .order_by(BUDDocument.updated_at.desc())
            .limit(limit)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def count_by_status_grouped(self) -> dict[BUDStatus, int]:
        """Count BUDs grouped by status for the org."""
        stmt = self._scoped(select(BUDDocument.status, func.count())).group_by(BUDDocument.status)
        result = await self._db.execute(stmt)
        return {row[0]: row[1] for row in result.all()}

    async def list_summaries_in_statuses(
        self, statuses: list[str], *, limit: int = 50
    ) -> list[tuple[int, str | None, BUDStatus]]:
        """Return ``(bud_number, title, status)`` for BUDs in any of ``statuses``,
        ordered by bud_number, capped at ``limit`` rows.
        """
        stmt = self._scoped(
            select(BUDDocument.bud_number, BUDDocument.title, BUDDocument.status)
            .where(BUDDocument.status.in_(statuses))
            .order_by(BUDDocument.bud_number)
            .limit(limit)
        )
        result = await self._db.execute(stmt)
        return [(row.bud_number, row.title, row.status) for row in result.all()]

    async def list_lagging_in_statuses(
        self, statuses: list[BUDStatus]
    ) -> list[tuple[int, str | None, BUDStatus]]:
        """BUDs in any of the given statuses past ``current_phase_deadline``.

        Returns ``(bud_number, title, status)`` tuples. Used by the
        standup risk-flag detector.
        """
        stmt = self._scoped(
            select(BUDDocument.bud_number, BUDDocument.title, BUDDocument.status).where(
                BUDDocument.status.in_(statuses),
                BUDDocument.current_phase_deadline.is_not(None),
                BUDDocument.current_phase_deadline < func.now(),
            )
        )
        result = await self._db.execute(stmt)
        return [(row.bud_number, row.title, row.status) for row in result.all()]

    async def get_impacted_repos(self, bud_id: uuid.UUID) -> list[dict] | None:
        """Return only the ``impacted_repos`` JSONB column for a BUD.

        Cheaper than fetching the full BUDDocument when only the impacted
        repos list is needed (e.g. agent activity simulation).

        Returns:
            The raw list of impacted-repo dicts, ``[]`` for an empty list,
            or ``None`` if the BUD does not exist in this org.
        """
        stmt = self._scoped(select(BUDDocument.impacted_repos).where(BUDDocument.id == bud_id))
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def exists_by_number(self, bud_number: int) -> bool:
        """Check if a BUD with this number exists in the scoped org."""
        stmt = self._scoped(
            select(BUDDocument.id).where(BUDDocument.bud_number == bud_number).limit(1)
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def get_minimal_info_by_ids(
        self, bud_ids: set[uuid.UUID]
    ) -> dict[uuid.UUID, dict[str, str | int]]:
        """Batch-resolve BUD ids to ``{"number", "title"}`` dicts.

        Args:
            bud_ids: Set of BUD UUIDs to look up within the scoped org.

        Returns:
            Mapping of bud_id -> {"number": int, "title": str}. Missing IDs absent.
        """
        if not bud_ids:
            return {}
        stmt = self._scoped(
            select(BUDDocument.id, BUDDocument.bud_number, BUDDocument.title).where(
                BUDDocument.id.in_(bud_ids)
            )
        )
        result = await self._db.execute(stmt)
        return {row.id: {"number": row.bud_number, "title": row.title} for row in result.all()}


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

    async def count_by_status(
        self,
        bud_id: uuid.UUID,
        status: BUDDesignStatus,
    ) -> int:
        """Count designs for a BUD with a given status."""
        stmt = self._scoped(
            select(func.count())
            .select_from(BUDDesign)
            .where(BUDDesign.bud_id == bud_id)
            .where(BUDDesign.status == status)
        )
        result = await self._db.execute(stmt)
        return result.scalar_one()

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
