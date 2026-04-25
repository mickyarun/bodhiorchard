# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Soft-delete + rollback helpers for the scan pipeline's destructive prelude.

A full-rescan flips every active scan-sourced feature to ``is_active=False``
so synthesis can rewrite a clean set. The IDs are stashed so that, if any
phase crashes before the rewrite finishes, ``rollback_soft_deleted_features``
can restore the original feature set rather than leaving the org with an
empty knowledge base.

Two functions:

- ``soft_delete_for_changed_repos`` — at scan start, pick the repos whose
  HEAD SHA actually moved (or every repo on a forced full rescan) and
  flip their feature_registry rows to ``is_active=False``. Returns the
  list of IDs the rollback needs.

- ``rollback_soft_deleted_features`` — on pipeline failure, reactivate
  those IDs in a **fresh session** (the pipeline's session may be
  poisoned). Includes a collision guard for the case where synthesis
  already re-created a feature with the same title as a soft-deleted
  row — those soft-deleted rows are superseded by the new ones, so
  hard-delete them instead of reactivating (and tripping the partial
  unique index ``uq_ki_org_title_feature_active``).

Lives in ``app.scan`` rather than ``app.services`` because both pieces
are called only from the orchestrator and exist purely to serve the
scan pipeline's transactional contract.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.knowledge_item import KnowledgeItem
from app.repositories.knowledge_item import KnowledgeItemRepository

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.repositories.tracked_repository import TrackedRepoRepository

logger = structlog.get_logger(__name__)


async def soft_delete_for_changed_repos(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    repo_paths: list[str],
    tracked_repo_repo: TrackedRepoRepository,
    full_rescan: bool,
) -> list[uuid.UUID]:
    """Soft-delete scan-sourced features for repos whose HEAD changed.

    Compares each active repo's current HEAD SHA against the SHA we
    stored on ``tracked_repositories.head_sha`` the last time a scan
    succeeded. Repos where the SHA matches skip deactivation entirely —
    their feature set is already consistent with the code state.

    When ``full_rescan`` is True, every active repo counts as changed
    regardless of SHA: the user explicitly asked for a full rebuild.

    Returns:
        The IDs that were soft-deleted. Callers stash this list so
        ``rollback_soft_deleted_features`` can restore exactly this
        set on pipeline failure.
    """
    from app.repositories.knowledge_item_scan import KnowledgeItemScanRepository
    from app.services.git_analyzer import get_head_sha

    changed_repo_ids: list[uuid.UUID] = []
    for path in repo_paths:
        tracked = await tracked_repo_repo.get_by_path(path)
        if tracked is None:
            # Untracked repo — no feature rows to soft-delete anyway.
            continue
        if full_rescan:
            changed_repo_ids.append(tracked.id)
            continue
        current_sha = await get_head_sha(path)
        if current_sha is None or current_sha != tracked.head_sha:
            changed_repo_ids.append(tracked.id)

    if not changed_repo_ids:
        return []

    ki_scan = KnowledgeItemScanRepository(db, org_id=org_id)
    return await ki_scan.soft_delete_by_repo_ids(changed_repo_ids)


async def rollback_soft_deleted_features(
    org_id: uuid.UUID,
    scan_id: str,
    deactivated_ids: list[uuid.UUID],
) -> None:
    """Reactivate the features soft-deleted by this scan run — with collision guard.

    Uses a fresh DB session since the original session may be in a bad state.

    **Why the collision guard matters.** If synthesis ran before the
    failure, it may have re-created a feature with the same title as one
    we soft-deleted at scan start. The partial unique index
    ``uq_ki_org_title_feature_active`` (``category='feature_registry'
    AND is_active=true``) treats both rows as duplicates on
    reactivation, raising ``UniqueViolationError``. We therefore:

    1. Look up which soft-deleted rows have a title already taken by an
       active row — those are **superseded**; we hard-delete them
       instead of reactivating (the new row is the correct data).
    2. Reactivate only the remaining set — rows whose title no longer
       has any active sibling.

    Args:
        org_id: Organization UUID.
        scan_id: Scan identifier for logging.
        deactivated_ids: IDs of items soft-deleted at scan start.
    """
    if not deactivated_ids:
        return

    try:
        async with AsyncSessionLocal() as recovery_db:
            # Pull the (id, title) pairs for the soft-deleted candidates.
            candidate_rows = await recovery_db.execute(
                select(KnowledgeItem.id, KnowledgeItem.title).where(
                    KnowledgeItem.org_id == org_id,
                    KnowledgeItem.id.in_(deactivated_ids),
                )
            )
            candidates = list(candidate_rows.all())
            if not candidates:
                return

            titles = {title for _, title in candidates}
            # Find titles that are currently held by an ACTIVE
            # feature_registry row — these slots are taken.
            active_rows = await recovery_db.execute(
                select(KnowledgeItem.title).where(
                    KnowledgeItem.org_id == org_id,
                    KnowledgeItem.category == "feature_registry",
                    KnowledgeItem.is_active.is_(True),
                    KnowledgeItem.title.in_(titles),
                )
            )
            taken_titles = {title for (title,) in active_rows.all()}

            superseded_ids = [cid for cid, title in candidates if title in taken_titles]
            restorable_ids = [cid for cid, title in candidates if title not in taken_titles]

            ki_recovery = KnowledgeItemRepository(recovery_db, org_id=org_id)
            purged = 0
            restored = 0
            if superseded_ids:
                # Their title now belongs to a newer active row — drop them.
                purged = await ki_recovery.delete_inactive_by_ids(superseded_ids)
            if restorable_ids:
                restored = await ki_recovery.reactivate_by_ids(restorable_ids)
            await recovery_db.commit()
            if restored or purged:
                logger.info(
                    "scan_rollback_restored_features",
                    scan_id=scan_id,
                    restored=restored,
                    purged_superseded=purged,
                )
    except Exception:
        logger.exception("scan_rollback_failed", scan_id=scan_id)
