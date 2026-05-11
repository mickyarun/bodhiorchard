# Copyright 2025-2026 Arun Rajkumar
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Soft-delete + rollback helpers for the scan pipeline's destructive prelude.

Two complementary paths under the incremental-CRUD model:

1. ``soft_delete_for_changed_repos`` — at scan start, pick the repos
   whose HEAD SHA actually moved (or every repo on a forced full rescan)
   and flip their scan-sourced features to ``is_active=False``. Stashed
   IDs feed the failure-rollback. The reconciler at end-of-synthesis
   revives any soft-deleted row whose cluster reappears (signature →
   Jaccard → cosine match), so legitimate continuity is preserved
   automatically; rows that nothing matched simply stay inactive.

2. ``rollback_soft_deleted_features`` — on pipeline failure before the
   reconciler can finish, reactivate the stashed IDs in a fresh
   session so the org doesn't lose features to a crashed scan. No
   collision guard is needed (unlike the legacy KI version): the new
   schema has no partial-unique-index on title, so a re-activate is
   always safe.

Lives in ``app.scan`` rather than ``app.services`` because both
pieces are called only from the orchestrator and exist purely to
serve the scan pipeline's transactional contract.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import structlog

from app.database import AsyncSessionLocal
from app.repositories.feature_scan import FeatureScanRepository
from app.services.git_analyzer import get_head_sha

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
    succeeded. Repos where the SHA matches skip deactivation entirely
    — their feature set is already consistent with the code state.

    When ``full_rescan`` is True, every active repo counts as changed
    regardless of SHA: the user explicitly asked for a full rebuild.

    Returns:
        The IDs that were soft-deleted. Callers stash this list so
        ``rollback_soft_deleted_features`` can restore exactly this
        set on pipeline failure.
    """
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

    feat_scan = FeatureScanRepository(db, org_id=org_id)
    return await feat_scan.soft_delete_by_repo_ids(changed_repo_ids)


async def rollback_soft_deleted_features(
    org_id: uuid.UUID,
    scan_id: str,
    deactivated_ids: list[uuid.UUID],
) -> None:
    """Reactivate the features soft-deleted by this scan run.

    Uses a fresh DB session since the original session may be in a
    bad state. No collision guard needed under the new schema — the
    partial unique index that tripped on KI revival doesn't exist on
    ``features`` (identity now lives on ``cluster_signature``, not
    title), so a re-activate is always safe even if synthesis already
    revived some of the same rows mid-flight.

    Args:
        org_id: Organization UUID.
        scan_id: Scan identifier for logging.
        deactivated_ids: IDs of features soft-deleted at scan start.
    """
    if not deactivated_ids:
        return

    try:
        async with AsyncSessionLocal() as recovery_db:
            feat_scan = FeatureScanRepository(recovery_db, org_id=org_id)
            restored = await feat_scan.reactivate_by_ids(deactivated_ids)
            await recovery_db.commit()
            if restored:
                logger.info(
                    "scan_rollback_restored_features",
                    scan_id=scan_id,
                    restored=restored,
                )
    except Exception:
        logger.exception("scan_rollback_failed", scan_id=scan_id)
