# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Feature deduplication for the scan pipeline.

Handles post-merge deduplication of concurrent MCP retries
(same title created multiple times).
"""

import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.knowledge_item import KnowledgeItemRepository

logger = structlog.get_logger(__name__)


async def dedup_merged_features(
    db: AsyncSession,
    org_id: uuid.UUID,
) -> int:
    """Remove duplicate feature items created by concurrent MCP calls.

    Claude CLI may retry ``write_feature_registry`` if the MCP bridge is slow,
    creating multiple items with the same title.  This keeps the newest item
    (highest id) and deactivates the rest.

    Returns:
        Number of duplicates deactivated.
    """
    ki_repo = KnowledgeItemRepository(db, org_id=org_id)
    dup_titles = await ki_repo.find_duplicate_titles("feature_registry")
    if not dup_titles:
        return 0

    total_deactivated = 0
    for title, _cnt in dup_titles:
        item_ids = await ki_repo.get_ids_by_title_ordered(title, "feature_registry")
        if len(item_ids) < 2:
            continue

        keep_id = item_ids[0]
        remove_ids = item_ids[1:]
        await ki_repo.transfer_repo_links(remove_ids, keep_id)
        total_deactivated += await ki_repo.bulk_deactivate_by_ids(remove_ids)
        logger.info(
            "dedup_merged_feature",
            title=title,
            kept=str(keep_id),
            removed=len(remove_ids),
        )

    if total_deactivated:
        await db.flush()
    return total_deactivated
