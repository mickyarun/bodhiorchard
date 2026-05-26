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
) -> dict[uuid.UUID, list[uuid.UUID]]:
    """Soft-delete features for changed repos.

    Returns the per-repo deactivated id partition. Empty dict on
    failure or no-op — the scan continues either way (soft-delete
    is best-effort; the merge audit catches duplicates downstream).
    """
    if not repo_paths:
        return {}
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
        return {}
    logger.info(
        "scan_soft_delete_done",
        scan_id=str(scan_id),
        repo_count=len(deactivated),
        feature_count=sum(len(ids) for ids in deactivated.values()),
    )
    return deactivated


async def rollback_soft_deleted(
    *,
    org_id: uuid.UUID,
    scan_id: uuid.UUID,
    deactivated_by_repo: dict[uuid.UUID, list[uuid.UUID]],
) -> None:
    """Reactivate every feature the soft-delete hook deactivated.

    Called from the orchestration-level failure handler when the
    fanout itself crashes (cancellation, system error). Per-repo
    failures are handled directly in ``_run_one`` via
    :func:`rollback_soft_deleted_for_repo` so siblings aren't
    affected. Both paths are idempotent — ``reactivate_by_ids``
    filters to currently-inactive rows.
    """
    total = sum(len(ids) for ids in deactivated_by_repo.values())
    if not total:
        return
    try:
        from app.scan.soft_delete import rollback_soft_deleted_features

        await rollback_soft_deleted_features(
            org_id=org_id,
            scan_id=str(scan_id),
            deactivated_by_repo=deactivated_by_repo,
        )
    except Exception:
        logger.exception(
            "scan_soft_delete_rollback_failed",
            scan_id=str(scan_id),
            count=total,
        )
        return
    logger.info(
        "scan_soft_delete_rolled_back",
        scan_id=str(scan_id),
        count=total,
    )


async def rollback_soft_deleted_for_repo(
    *,
    org_id: uuid.UUID,
    scan_id: uuid.UUID,
    repo_id: uuid.UUID,
    feature_ids: list[uuid.UUID],
) -> None:
    """Reactivate one repo's soft-deleted slice after its workflow fails.

    Bridges the orchestrator's per-repo failure handler to the
    underlying helper so the runner module stays free of direct
    ``app.scan.*`` imports (the established layering — scan-pipeline
    services depend on ``app.scan`` only through these hooks).
    """
    if not feature_ids:
        return
    try:
        from app.scan.soft_delete import rollback_soft_deleted_for_repo as _impl

        await _impl(
            org_id=org_id,
            scan_id=str(scan_id),
            repo_id=repo_id,
            feature_ids=feature_ids,
        )
    except Exception:
        logger.exception(
            "scan_soft_delete_repo_rollback_failed",
            scan_id=str(scan_id),
            repo_id=str(repo_id),
            count=len(feature_ids),
        )
