# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Data access repositories for Jira import models.

Provides tenant-scoped CRUD plus dedup-specific queries for
``JiraImportSession`` and ``JiraIssueBudMap``.
"""

import uuid

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.jira_import import ImportStatus, JiraImportSession, JiraIssueBudMap, MapStatus
from app.repositories.base import BaseRepository

# ── Startup recovery ──────────────────────────────────────────────


async def recover_stuck_import_sessions(db: AsyncSession) -> int:
    """Mark sessions stuck in RUNNING/DISCOVERING as FAILED on startup.

    Mirrors the pattern in ``bud_agent_task.recover_stuck_agent_tasks()``.
    Called once during app lifespan before serving requests.

    Returns:
        Number of sessions marked as failed.
    """
    stmt = (
        update(JiraImportSession)
        .where(
            JiraImportSession.status.in_(
                [
                    ImportStatus.RUNNING,
                    ImportStatus.DISCOVERING,
                ]
            )
        )
        .values(
            status=ImportStatus.FAILED,
            error="Server restarted while import was in progress",
        )
    )
    result = await db.execute(stmt)
    await db.flush()
    return result.rowcount or 0


# ── Session Repository ────────────────────────────────────────────


class JiraImportSessionRepository(BaseRepository[JiraImportSession]):
    """Repository for Jira import sessions, scoped to an organization."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        super().__init__(JiraImportSession, db, org_id=org_id)

    async def list_sessions(self) -> list[JiraImportSession]:
        """List all import sessions for the org, most recent first."""
        stmt = self._scoped(
            select(JiraImportSession).order_by(JiraImportSession.created_at.desc())
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def get_latest_for_project(self, project_key: str) -> JiraImportSession | None:
        """Get the most recent session for a given Jira project key."""
        stmt = self._scoped(
            select(JiraImportSession)
            .where(JiraImportSession.jira_project_key == project_key)
            .order_by(JiraImportSession.created_at.desc())
            .limit(1)
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def update_status(
        self,
        session_id: uuid.UUID,
        status: str,
        *,
        error: str | None = None,
    ) -> None:
        """Update a session's status and optionally set an error."""
        values: dict = {"status": status}
        if error is not None:
            values["error"] = error[:2000]
        stmt = (
            update(JiraImportSession)
            .where(JiraImportSession.id == session_id)
            .where(JiraImportSession.org_id == self._org_id)
            .values(**values)
        )
        await self._db.execute(stmt)
        await self._db.flush()

    async def update_progress(
        self,
        session_id: uuid.UUID,
        processed_count: int,
        last_processed_key: str,
    ) -> None:
        """Checkpoint progress for crash recovery."""
        stmt = (
            update(JiraImportSession)
            .where(JiraImportSession.id == session_id)
            .where(JiraImportSession.org_id == self._org_id)
            .values(
                processed_count=processed_count,
                last_processed_key=last_processed_key,
            )
        )
        await self._db.execute(stmt)
        await self._db.flush()


# ── Map Repository ────────────────────────────────────────────────


class JiraIssueBudMapRepository(BaseRepository[JiraIssueBudMap]):
    """Repository for Jira issue-to-BUD/Bug mappings."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        super().__init__(JiraIssueBudMap, db, org_id=org_id)

    async def get_by_jira_key(self, jira_key: str) -> JiraIssueBudMap | None:
        """Look up a mapping by Jira issue key (for Layer 1 dedup)."""
        stmt = self._scoped(
            select(JiraIssueBudMap).where(JiraIssueBudMap.jira_issue_key == jira_key)
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_existing_keys_for_org(self) -> set[str]:
        """Return Jira keys that were successfully imported for this org.

        Only includes keys that have a linked BUD or Bug (not orphaned
        map entries from failed sessions). Used for bulk Layer 1 dedup.
        """
        stmt = self._scoped(
            select(JiraIssueBudMap.jira_issue_key).where(
                JiraIssueBudMap.status.in_(
                    [
                        MapStatus.IMPORTED,
                        MapStatus.CONSOLIDATED,
                        MapStatus.DUPLICATE_CANDIDATE,
                    ]
                ),
                or_(
                    JiraIssueBudMap.bud_id.is_not(None),
                    JiraIssueBudMap.bug_id.is_not(None),
                ),
            )
        )
        result = await self._db.execute(stmt)
        return set(result.scalars().all())

    async def list_for_session(
        self,
        session_id: uuid.UUID,
        *,
        status: str | None = None,
    ) -> list[JiraIssueBudMap]:
        """List all mappings for a given import session.

        Args:
            session_id: The import session UUID.
            status: Optional filter by map status.
        """
        stmt = self._scoped(
            select(JiraIssueBudMap)
            .where(JiraIssueBudMap.import_session_id == session_id)
            .order_by(JiraIssueBudMap.jira_issue_key)
        )
        if status:
            stmt = stmt.where(JiraIssueBudMap.status == status)
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def count_by_status(self, session_id: uuid.UUID) -> dict[str, int]:
        """Count mappings grouped by status for a session.

        Returns:
            Dict like ``{"imported": 42, "skipped": 3, ...}``.
        """
        stmt = self._scoped(
            select(JiraIssueBudMap.status, func.count(JiraIssueBudMap.id)).where(
                JiraIssueBudMap.import_session_id == session_id
            )
        ).group_by(JiraIssueBudMap.status)
        result = await self._db.execute(stmt)
        return dict(result.all())

    async def bulk_add(self, maps: list[JiraIssueBudMap]) -> None:
        """Add multiple map entries without individual flushes."""
        for m in maps:
            self._db.add(m)
        await self._db.flush()

    async def mark_status(
        self,
        map_id: uuid.UUID,
        status: str,
        *,
        bud_id: uuid.UUID | None = None,
        bug_id: uuid.UUID | None = None,
        note: str | None = None,
        error: str | None = None,
        consolidated_into: str | None = None,
    ) -> None:
        """Update a single mapping's status and linked IDs."""
        values: dict = {"status": status}
        if bud_id is not None:
            values["bud_id"] = bud_id
        if bug_id is not None:
            values["bug_id"] = bug_id
        if note is not None:
            values["note"] = note
        if error is not None:
            values["error"] = error[:500]
        if consolidated_into is not None:
            values["consolidated_into"] = consolidated_into
        stmt = (
            update(JiraIssueBudMap)
            .where(JiraIssueBudMap.id == map_id)
            .where(JiraIssueBudMap.org_id == self._org_id)
            .values(**values)
        )
        await self._db.execute(stmt)

    async def get_review_needed(self, session_id: uuid.UUID) -> list[JiraIssueBudMap]:
        """Get items flagged for manual duplicate review."""
        return await self.list_for_session(session_id, status=MapStatus.REVIEW_NEEDED)

    async def list_imported_bud_ids_for_session(self, session_id: uuid.UUID) -> list[uuid.UUID]:
        """Distinct ``bud_id`` values for IMPORTED entries in a session."""
        stmt = self._scoped(
            select(JiraIssueBudMap.bud_id).where(
                JiraIssueBudMap.import_session_id == session_id,
                JiraIssueBudMap.status == MapStatus.IMPORTED,
                JiraIssueBudMap.bud_id.is_not(None),
            )
        ).distinct()
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def delete_by_id(self, entry_id: uuid.UUID) -> None:
        """Delete a single map entry by id (org-scoped)."""
        stmt = delete(JiraIssueBudMap).where(
            JiraIssueBudMap.id == entry_id,
            JiraIssueBudMap.org_id == self._org_id,
        )
        await self._db.execute(stmt)
        await self._db.flush()

    async def delete_orphaned(self, *, valid_bud_ids_select, valid_bug_ids_select) -> int:
        """Delete map entries whose bud/bug links no longer resolve.

        Three passes (single tx):
        - Entries pointing to a bud_id not in ``valid_bud_ids_select``
        - Entries pointing to a bug_id not in ``valid_bug_ids_select``
        - Entries with both ids null (stale from abandoned imports)
        """
        stmt1 = delete(JiraIssueBudMap).where(
            JiraIssueBudMap.org_id == self._org_id,
            JiraIssueBudMap.bud_id.is_not(None),
            ~JiraIssueBudMap.bud_id.in_(valid_bud_ids_select),
        )
        r1 = await self._db.execute(stmt1)
        stmt2 = delete(JiraIssueBudMap).where(
            JiraIssueBudMap.org_id == self._org_id,
            JiraIssueBudMap.bug_id.is_not(None),
            ~JiraIssueBudMap.bug_id.in_(valid_bug_ids_select),
        )
        r2 = await self._db.execute(stmt2)
        stmt3 = delete(JiraIssueBudMap).where(
            JiraIssueBudMap.org_id == self._org_id,
            JiraIssueBudMap.bud_id.is_(None),
            JiraIssueBudMap.bug_id.is_(None),
        )
        r3 = await self._db.execute(stmt3)
        return (r1.rowcount or 0) + (r2.rowcount or 0) + (r3.rowcount or 0)

    async def delete_pending_for_session(self, session_id: uuid.UUID) -> int:
        """Delete pending map entries from a session (cleanup before re-run).

        Only deletes entries with status ``pending`` — successfully imported
        entries are preserved.
        """
        stmt = (
            delete(JiraIssueBudMap)
            .where(JiraIssueBudMap.import_session_id == session_id)
            .where(JiraIssueBudMap.org_id == self._org_id)
            .where(JiraIssueBudMap.status == MapStatus.PENDING)
        )
        result = await self._db.execute(stmt)
        await self._db.flush()
        return result.rowcount or 0
