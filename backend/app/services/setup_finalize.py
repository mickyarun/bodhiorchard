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

"""Stage-2 of the wizard: register repos and kick off scanning.

Two paths land here, both gated by :func:`setup_init_org` having
already created the org:

- **Legacy** (``source_code`` payload) — pre-cloned local paths with
  branch mappings; delegated to
  :func:`app.services.setup_finalize_legacy.finalize_legacy_source_code`
  so this dispatcher stays under the 200-line ceiling.
- **App** (``installable_items`` payload) — full names that the org's
  GitHub-App installation can see; we enqueue a
  ``JOB_REPO_BULK_ONBOARD`` job which clones, registers, then triggers
  the scan asynchronously.

Idempotency: the App path checks for an active bulk-onboard job for
this org before enqueueing a duplicate. The legacy path is
idempotent through ``TrackedRepoRepository.upsert`` (composite unique
on ``(org_id, path)``) and only kicks the scan once per call.
"""

from __future__ import annotations

import uuid

import structlog
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization import Organization
from app.models.user import User
from app.schemas.jobs import (
    BulkOnboardItemProgress,
    BulkOnboardItemState,
    BulkOnboardJobPayload,
)
from app.schemas.repo_install import AppInstallState, BulkOnboardItem
from app.schemas.setup import (
    FinalizeWithReposRequest,
    FinalizeWithReposResponse,
)
from app.services.github_install_repos import (
    list_installation_repos,
    resolve_app_install_state,
)
from app.services.job_queue import (
    JOB_REPO_BULK_ONBOARD,
    create_job,
    is_job_active,
)
from app.services.setup_finalize_legacy import finalize_legacy_source_code

logger = structlog.get_logger(__name__)


def _build_bulk_payload(org_id: uuid.UUID, items: list[BulkOnboardItem]) -> BulkOnboardJobPayload:
    """Translate wizard items into the job-queue payload shape."""
    return BulkOnboardJobPayload(
        org_id=org_id,
        items=[
            BulkOnboardItemProgress(
                full_name=item.full_name,
                main_branch=item.main_branch,
                develop_branch=item.develop_branch,
                uat_branch=item.uat_branch,
                status=BulkOnboardItemState.PENDING,
            )
            for item in items
        ],
    )


async def _finalize_app_path(
    *,
    org: Organization,
    items: list[BulkOnboardItem],
    user: User,
    db: AsyncSession,
) -> str:
    """Validate the install + items, then enqueue a bulk-onboard job."""
    state, _install_url = resolve_app_install_state(org)
    if state is not AppInstallState.READY:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="GitHub App installation is not ready.",
        )

    installable = await list_installation_repos(org, db)
    installable_names = {item.full_name for item in installable}
    unknown = [item.full_name for item in items if item.full_name not in installable_names]
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Repos not in installation set: {', '.join(unknown)}",
        )

    # Idempotency: if a bulk-onboard for this org is already running,
    # the duplicate would just re-clone everything. We log but don't
    # short-circuit — TrackedRepoRepository.upsert is idempotent so
    # the duplicate job is safe; logging is enough to spot it in ops.
    if is_job_active(JOB_REPO_BULK_ONBOARD, {"org_id": str(org.id)}):
        logger.info("setup_finalize_app_path_dedup_active", org_id=str(org.id))

    payload = _build_bulk_payload(org.id, items)
    job = create_job(
        JOB_REPO_BULK_ONBOARD,
        payload=payload.model_dump(mode="json"),
        user_id=str(user.id),
    )
    logger.info(
        "setup_finalize_app_path_job_enqueued",
        job_id=job.job_id,
        org_id=str(org.id),
        item_count=len(items),
    )
    return job.job_id


async def setup_finalize_with_repos(
    *,
    org: Organization,
    user: User,
    req: FinalizeWithReposRequest,
    db: AsyncSession,
) -> FinalizeWithReposResponse:
    """Dispatch to the App path or the legacy path and return the result.

    ``req`` is already XOR-validated by its model validator; both
    branches below trust that exactly one of the two payload arms is
    populated.
    """
    if req.installable_items:
        job_id = await _finalize_app_path(
            org=org,
            items=req.installable_items,
            user=user,
            db=db,
        )
        return FinalizeWithReposResponse(
            scan_id=None,
            job_id=job_id,
            is_setup_complete=True,
            embedding_warning=None,
        )

    assert req.source_code is not None  # XOR-validated by the schema.
    result = await finalize_legacy_source_code(org=org, source_code=req.source_code, db=db)
    return FinalizeWithReposResponse(
        scan_id=result.scan_id,
        job_id=None,
        is_setup_complete=True,
        embedding_warning=result.embedding_warning,
    )
