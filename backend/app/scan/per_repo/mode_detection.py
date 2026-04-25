# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Phase A — pick incremental vs full mode for one repo.

Owns one decision: given the prior ``head_sha`` we stored on this repo
and the current state of ``knowledge_items``, do we walk the whole
repo from scratch or apply a diff since ``last_sha``? The answer
flows downstream into stale-cleanup gating, the synthesis prompt
shape, and skill extraction's ``feature_map`` lookup.

Three early-out branches in priority order:

1. ``full_rescan=True`` was passed in (user pressed Reindex / Reset).
2. ``last_sha`` exists but no ``feature_registry`` rows survive — we
   were soft-deleted between scans, so a "diff since" walk would
   reanalyse against an empty world. Fall through to full mode.
3. The change ratio crosses ``INCREMENTAL_THRESHOLD`` — too much has
   changed, full is faster and safer than reconciling deletes.

Otherwise: incremental, return only the deleted-file list so the
stale-cleanup phase can deactivate the corresponding KIs.
"""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.knowledge_item import KnowledgeItemRepository
from app.services.git_analyzer import get_diff_since

logger = structlog.get_logger(__name__)


async def phase_a_scan_mode(
    db: AsyncSession,
    org_id: uuid.UUID,
    repo_path: str,
    repo_name: str,
    full_rescan: bool,
    last_sha: str | None,
    ki_repo: KnowledgeItemRepository,
    scan_id: str,
) -> tuple[bool, bool, list[str]]:
    """Phase A: Determine scan mode (incremental vs full).

    Args:
        db: Async database session.
        org_id: Organization UUID.
        repo_path: Absolute path to the repository.
        repo_name: Name of the repository.
        full_rescan: Whether the user forced a full rescan.
        last_sha: Last known commit SHA, or None.
        ki_repo: Knowledge item repository instance.
        scan_id: Scan identifier for logging.

    Returns:
        Tuple of (is_incremental, full_rescan, deleted_files).
        ``full_rescan`` may be updated to True if no scan features exist.
    """
    # Local import to break the scan_pipeline ↔ scan_phases legacy cycle.
    # ``INCREMENTAL_THRESHOLD`` is a module-level constant in scan_pipeline;
    # importing at module top would re-introduce the cycle.
    from app.services.scan_pipeline import INCREMENTAL_THRESHOLD

    del db, org_id  # accepted for the legacy signature; not used in this body

    is_incremental = False
    deleted_files: list[str] = []

    # Check if we have any scan-sourced features — if not, force
    # full scan even if last_sha exists.
    if not full_rescan and last_sha:
        has_scan_features = await ki_repo.has_any(source="scan")
        if not has_scan_features:
            logger.info(
                "scan_force_full_no_scan_features",
                scan_id=scan_id,
                repo=repo_name,
            )
            full_rescan = True

    if not full_rescan and last_sha:
        diff = await get_diff_since(repo_path, last_sha)
        total_changed = len(diff.changed_files) + len(diff.deleted_files)

        change_ratio = total_changed / diff.total_repo_files if diff.total_repo_files > 0 else 1.0

        if change_ratio <= INCREMENTAL_THRESHOLD and total_changed > 0:
            is_incremental = True
            deleted_files = diff.deleted_files
        elif total_changed == 0:
            is_incremental = True
        else:
            logger.info(
                "scan_full_threshold_exceeded",
                scan_id=scan_id,
                repo=repo_name,
                ratio=round(change_ratio, 3),
            )
    else:
        logger.info(
            "scan_full",
            scan_id=scan_id,
            repo=repo_name,
            reason="first_run" if not last_sha else "forced",
        )

    return is_incremental, full_rescan, deleted_files
