# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Soft-delete pre/post hooks for scans.

Wraps ``app.scan.soft_delete.soft_delete_for_changed_repos`` and
``rollback_soft_deleted_features`` so the ``scan_runner`` can
preserve the same data-safety invariants the legacy pipeline has:

* Before the per-repo workflows fan out, soft-delete every active
  feature row whose repo is *changed* (HEAD SHA differs from
  ``tracked_repositories.head_sha``). This frees their ``title`` so
  fresh synthesis can write under the same key.
* On orchestration failure, reactivate exactly that set so we don't
  lose features when a scan crashes mid-flight.

Hooks are best-effort — soft-delete failures degrade behaviour but
don't abort the scan (the merge audit will surface duplicates).
"""

from __future__ import annotations

import uuid

import structlog

from app.repositories.tracked_repository import TrackedRepoRepository
from app.scan.session import with_session

logger = structlog.get_logger(__name__)


async def soft_delete_changed_repos(
    *,
    org_id: uuid.UUID,
    scan_id: uuid.UUID,
    repo_paths: list[str],
    full_rescan: bool,
) -> list[uuid.UUID]:
    """Soft-delete features for changed repos. Returns the deactivated ids."""
    if not repo_paths:
        return []
    try:
        async with with_session(org_id) as db:
            from app.scan.soft_delete import soft_delete_for_changed_repos

            tracked_repo_repo = TrackedRepoRepository(db, org_id=org_id)
            deactivated = await soft_delete_for_changed_repos(
                db,
                org_id=org_id,
                repo_paths=repo_paths,
                tracked_repo_repo=tracked_repo_repo,
                full_rescan=full_rescan,
            )
            await db.commit()
    except Exception:
        logger.exception(
            "scan_soft_delete_failed",
            scan_id=str(scan_id),
            repo_count=len(repo_paths),
        )
        return []
    logger.info(
        "scan_soft_delete_done",
        scan_id=str(scan_id),
        deactivated=len(deactivated),
    )
    return deactivated


async def rollback_soft_deleted(
    *,
    org_id: uuid.UUID,
    scan_id: uuid.UUID,
    deactivated_ids: list[uuid.UUID],
) -> None:
    """Reactivate features the soft-delete hook deactivated, if any.

    Called only when the scan ends in FAILED. The legacy helper opens
    its own session inside, so we just dispatch.
    """
    if not deactivated_ids:
        return
    try:
        from app.scan.soft_delete import rollback_soft_deleted_features

        await rollback_soft_deleted_features(
            org_id=org_id,
            scan_id=str(scan_id),
            deactivated_ids=deactivated_ids,
        )
    except Exception:
        logger.exception(
            "scan_soft_delete_rollback_failed",
            scan_id=str(scan_id),
            count=len(deactivated_ids),
        )
        return
    logger.info(
        "scan_soft_delete_rolled_back",
        scan_id=str(scan_id),
        count=len(deactivated_ids),
    )
