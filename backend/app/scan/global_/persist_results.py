# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Phase G — final commit of scan results.

Runs once at the end of every successful scan. Two writes:

1. ``tracked_repositories.head_sha`` + ``last_scanned_at`` per repo so
   the next scan's ``phase_a_scan_mode`` can decide incremental vs full.
2. ``organizations.config.knowledge.last_scan`` snapshot — the read
   path for the Settings → Code Index stats card.

This is the only place that calls ``db.commit()`` in the pipeline's
sequential body; everything before it is flushed-but-uncommitted, so
``phase_g_persist`` is also the gate that turns "scan succeeded in
memory" into "scan succeeded on disk".
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.knowledge_item import KnowledgeItemRepository

logger = structlog.get_logger(__name__)


async def phase_g_persist(
    db: AsyncSession,
    org_id: uuid.UUID,
    repo_paths: list[str],
    new_shas: dict[str, str],
    config: dict,
    total_profiles: int,
    all_unmatched: list[str],
    overall_mode: str,
    ki_repo: KnowledgeItemRepository,
) -> int:
    """Phase G: Save last commit SHAs + scan results to org config.

    Args:
        db: Async database session.
        org_id: Organization UUID.
        repo_paths: List of all repo paths scanned.
        new_shas: Mapping of repo_path → HEAD SHA.
        config: Organization config dict to update.
        total_profiles: Total skill profiles found.
        all_unmatched: List of unmatched author emails.
        overall_mode: Scan mode ('full' or 'incremental').
        ki_repo: Knowledge item repository instance.

    Returns:
        Authoritative feature count from DB.
    """
    from app.repositories.organization import OrganizationRepository
    from app.repositories.tracked_repository import TrackedRepoRepository

    tracked_repo_repo = TrackedRepoRepository(db, org_id=org_id)

    # Update tracked_repositories with new SHAs and counts
    for rp, sha in new_shas.items():
        tracked = await tracked_repo_repo.get_by_path(rp)
        if tracked:
            k_count = await ki_repo.count_by_repo_id(tracked.id)
            f_count = await ki_repo.count_by_repo_id(tracked.id, category="feature_registry")
            await tracked_repo_repo.update_after_scan(rp, sha, k_count, f_count)

    # Authoritative feature count from DB
    actual_features = await ki_repo.count_active(category="feature_registry")

    # Legacy config compat
    config.setdefault("knowledge", {})
    config["knowledge"]["repo_shas"] = new_shas
    if len(repo_paths) == 1 and new_shas:
        config["knowledge"]["last_commit_sha"] = next(iter(new_shas.values()))

    # Persist last scan results for the stats endpoint
    config["knowledge"]["last_scan"] = {
        "completed_at": datetime.now(UTC).isoformat(),
        "repos_scanned": len(repo_paths),
        "features_indexed": actual_features,
        "profiles_found": total_profiles,
        "unmatched_authors": len(all_unmatched),
        "scan_mode": overall_mode,
    }

    org_repo = OrganizationRepository(db)
    org = await org_repo.get_by_id(org_id)
    org.config = config
    await db.flush()
    await db.commit()

    return actual_features
