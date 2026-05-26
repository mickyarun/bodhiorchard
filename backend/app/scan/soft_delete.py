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
) -> dict[uuid.UUID, list[uuid.UUID]]:
    """Soft-delete scan-sourced features for repos whose HEAD changed.

    Compares each active repo's current HEAD SHA against the SHA we
    stored on ``tracked_repositories.head_sha`` the last time a scan
    succeeded. Repos where the SHA matches skip deactivation entirely
    — their feature set is already consistent with the code state.

    When ``full_rescan`` is True, every active repo counts as changed
    regardless of SHA: the user explicitly asked for a full rebuild.

    Returns:
        ``{repo_id: [feature_id, ...]}`` for every changed repo that
        had at least one row soft-deleted. The per-repo partition
        lets the orchestrator roll back exactly the failed repo's
        slice when its synthesis fails, without disturbing siblings
        whose synthesis legitimately marked features inactive.
    """
    changed_repo_ids: list[uuid.UUID] = []
    head_sha_by_repo: dict[uuid.UUID, str] = {}
    for path in repo_paths:
        tracked = await tracked_repo_repo.get_by_path(path)
        if tracked is None:
            # Untracked repo — no feature rows to soft-delete anyway.
            continue
        # Resolve the on-disk HEAD; falls back to the stored SHA when
        # the working copy can't be inspected so the stamp survives
        # filesystem hiccups (the stored SHA is still the right
        # "features were last current at this commit" pointer).
        current_sha = await get_head_sha(path)
        stamp_sha = current_sha or tracked.head_sha
        if stamp_sha:
            head_sha_by_repo[tracked.id] = stamp_sha
        if full_rescan:
            changed_repo_ids.append(tracked.id)
            continue
        if current_sha is None or current_sha != tracked.head_sha:
            changed_repo_ids.append(tracked.id)

    if not changed_repo_ids:
        return {}

    feat_scan = FeatureScanRepository(db, org_id=org_id)
    return await feat_scan.soft_delete_by_repo_ids(
        changed_repo_ids,
        head_sha_by_repo=head_sha_by_repo,
    )


async def rollback_soft_deleted_features(
    org_id: uuid.UUID,
    scan_id: str,
    deactivated_by_repo: dict[uuid.UUID, list[uuid.UUID]],
) -> None:
    """Reactivate every feature soft-deleted by this scan run.

    Uses a fresh DB session since the original session may be in a
    bad state. No collision guard needed under the new schema — the
    partial unique index that tripped on KI revival doesn't exist on
    ``features`` (identity now lives on ``cluster_signature``, not
    title), so a re-activate is always safe even if synthesis already
    revived some of the same rows mid-flight (``reactivate_by_ids``
    filters to currently-inactive rows for idempotency).

    Args:
        org_id: Organization UUID.
        scan_id: Scan identifier for logging.
        deactivated_by_repo: ``{repo_id: [feature_id, ...]}`` from
            :func:`soft_delete_for_changed_repos`.
    """
    flat = [fid for ids in deactivated_by_repo.values() for fid in ids]
    if not flat:
        return

    try:
        async with AsyncSessionLocal() as recovery_db:
            feat_scan = FeatureScanRepository(recovery_db, org_id=org_id)
            restored = await feat_scan.reactivate_by_ids(flat)
            await recovery_db.commit()
            if restored:
                logger.info(
                    "scan_rollback_restored_features",
                    scan_id=scan_id,
                    restored=restored,
                )
    except Exception:
        logger.exception("scan_rollback_failed", scan_id=scan_id)


async def rollback_soft_deleted_for_repo(
    org_id: uuid.UUID,
    scan_id: str,
    repo_id: uuid.UUID,
    feature_ids: list[uuid.UUID],
) -> None:
    """Reactivate exactly the soft-deleted slice for one failed repo.

    Companion of :func:`rollback_soft_deleted_features` for the
    per-repo failure path: when one repo's synthesis fails but the
    rest of the scan continues, we want to restore *only* that
    repo's slice — siblings whose synthesis succeeded may have
    legitimately marked some of their features inactive, and we
    must not resurrect those.

    Args:
        org_id: Organization UUID.
        scan_id: Scan identifier for logging.
        repo_id: Repo whose slice is being rolled back (logged only —
            ``feature_ids`` is the authoritative selector).
        feature_ids: Feature IDs to reactivate; the caller pulls this
            from the per-repo dict returned by soft-delete.
    """
    if not feature_ids:
        return

    try:
        async with AsyncSessionLocal() as recovery_db:
            feat_scan = FeatureScanRepository(recovery_db, org_id=org_id)
            restored = await feat_scan.reactivate_by_ids(feature_ids)
            await recovery_db.commit()
            if restored:
                logger.info(
                    "scan_rollback_restored_features_for_repo",
                    scan_id=scan_id,
                    repo_id=str(repo_id),
                    restored=restored,
                )
    except Exception:
        logger.exception(
            "scan_rollback_for_repo_failed",
            scan_id=scan_id,
            repo_id=str(repo_id),
        )
