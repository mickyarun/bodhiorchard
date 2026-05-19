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

"""Design system management endpoints."""

import uuid
from pathlib import Path
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db, require_permissions
from app.models.user import User
from app.repositories.design_system import DesignSystemRefRepository
from app.repositories.tracked_repository import TrackedRepoRepository
from app.schemas.design_system import (
    DesignSystemExtractRequest,
    DesignSystemRead,
    DesignSystemSetDefault,
    DesignSystemUpdateCustomContent,
)
from app.schemas.jobs import DesignExtractJobPayload, JobCreatedResponse
from app.services.job_queue import JOB_DESIGN_EXTRACT, create_job

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["design-systems"])


async def _to_read(
    repo: DesignSystemRefRepository,
    ds_id: uuid.UUID,
) -> dict[str, Any]:
    """Return the `DesignSystemRead` shape for one row.

    Goes through ``list_with_repo_names`` so the response shape (including
    ``merged_content`` and the joined ``repo_name``) stays defined in one
    place. Endpoints that just mutated a row call this to read it back.
    """
    items = await repo.list_with_repo_names()
    for item in items:
        if item["id"] == ds_id:
            return item
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Design system not found",
    )


@router.get(
    "/",
    response_model=list[DesignSystemRead],
    dependencies=[Depends(require_permissions("settings:view"))],
)
async def list_design_systems(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """List all design systems for the current org with repo names.

    Args:
        current_user: The authenticated user.
        db: The async database session.

    Returns:
        A list of design system entries with joined repo names.
    """
    repo = DesignSystemRefRepository(db, org_id=current_user.org_id)
    return await repo.list_with_repo_names()


@router.get(
    "/{ds_id}",
    response_model=DesignSystemRead,
    dependencies=[Depends(require_permissions("settings:view"))],
)
async def get_design_system(
    ds_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get a specific design system by ID.

    Args:
        ds_id: The design system UUID.
        current_user: The authenticated user.
        db: The async database session.

    Returns:
        The design system entry.

    Raises:
        HTTPException: If not found.
    """
    repo = DesignSystemRefRepository(db, org_id=current_user.org_id)
    ds = await repo.get_by_id(ds_id)
    if ds is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Design system not found"
        )
    return await _to_read(repo, ds_id)


@router.post(
    "/extract",
    response_model=JobCreatedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_permissions("settings:edit"))],
)
async def extract_design_system(
    body: DesignSystemExtractRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JobCreatedResponse:
    """Submit a design system extraction job for async processing.

    Returns immediately with a job ID. The frontend tracks progress
    via WebSocket (job:{jobId} topic) or polling GET /v1/jobs/{jobId}/status.

    Args:
        body: Extract request with repo_id and is_default flag.
        current_user: The authenticated user.
        db: The async database session.

    Returns:
        JobCreatedResponse with the job ID to track.
    """
    tracked_repo_repo = TrackedRepoRepository(db, org_id=current_user.org_id)
    tracked_repo = await tracked_repo_repo.get_by_id(body.repo_id)
    if tracked_repo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Tracked repository not found"
        )

    repo_path = Path(tracked_repo.path)
    if not repo_path.exists():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Repository path does not exist: {tracked_repo.path}",
        )

    from app.services.platforms import UI_KINDS, detect_platform

    platform = detect_platform(repo_path)
    if platform is None or platform.kind not in UI_KINDS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"No UI-bearing platform detected at {repo_path}. Design-system "
                "extraction is only supported for frontend / mobile / desktop / "
                "static-site / design-tokens repositories."
            ),
        )

    payload = DesignExtractJobPayload(
        org_id=str(current_user.org_id),
        repo_id=str(body.repo_id),
        repo_path=str(repo_path),
        is_default=body.is_default,
        platform=platform.slug,
    )

    job = create_job(
        JOB_DESIGN_EXTRACT,
        payload=payload.model_dump(),
        user_id=str(current_user.id),
    )

    logger.info(
        "design_extract_job_created",
        job_id=job.job_id,
        repo=tracked_repo.name,
    )

    return JobCreatedResponse(job_id=job.job_id)


@router.post(
    "/set-default",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permissions("settings:edit"))],
)
async def set_default_design_system(
    body: DesignSystemSetDefault,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Mark a design system as the org-wide default.

    Args:
        body: Contains the ID to make default.
        current_user: The authenticated user.
        db: The async database session.

    Raises:
        HTTPException: If the design system is not found.
    """
    ds_repo = DesignSystemRefRepository(db, org_id=current_user.org_id)
    ds = await ds_repo.get_by_id(body.id)
    if ds is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Design system not found"
        )
    await ds_repo.set_default(body.id)
    logger.info("design_system_default_set", ds_id=str(body.id))


@router.put(
    "/{ds_id}",
    response_model=DesignSystemRead,
    dependencies=[Depends(require_permissions("settings:edit"))],
)
async def update_design_system_custom_content(
    ds_id: uuid.UUID,
    body: DesignSystemUpdateCustomContent,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Write the user-owned customisation layer for a design system.

    The extractor's ``content`` field is untouched; only ``custom_content``
    is written. Re-scans, PR-merge rescans, and forced ``/extract`` runs
    flow through :meth:`DesignSystemRefRepository.upsert`, which never
    references this column — so edits saved here survive every re-extraction.

    Pass an empty / whitespace-only string to clear the customisation;
    :meth:`DesignSystemRefRepository.set_custom_content` normalises to
    ``None`` so the ``is_customised`` flag stays truthful.
    """
    ds_repo = DesignSystemRefRepository(db, org_id=current_user.org_id)
    ds = await ds_repo.get_by_id(ds_id)
    if ds is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Design system not found"
        )

    await ds_repo.set_custom_content(ds, body.custom_content)

    logger.info(
        "design_system_custom_content_updated",
        ds_id=str(ds_id),
        cleared=ds.custom_content is None,
    )

    return await _to_read(ds_repo, ds_id)


@router.post(
    "/{ds_id}/reset-customisations",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permissions("settings:edit"))],
)
async def reset_design_system_customisations(
    ds_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Drop the user customisation layer back to the extracted defaults.

    Equivalent to ``PUT /{ds_id}`` with an empty body, exposed separately
    so the frontend can offer a discoverable "Revert" affordance without
    asking the user to clear a textarea by hand.
    """
    ds_repo = DesignSystemRefRepository(db, org_id=current_user.org_id)
    ds = await ds_repo.get_by_id(ds_id)
    if ds is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Design system not found"
        )
    await ds_repo.set_custom_content(ds, None)
    logger.info("design_system_customisations_reset", ds_id=str(ds_id))


@router.delete(
    "/{ds_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permissions("settings:edit"))],
)
async def delete_design_system(
    ds_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a design system entry.

    Args:
        ds_id: The design system UUID.
        current_user: The authenticated user.
        db: The async database session.

    Raises:
        HTTPException: If not found.
    """
    ds_repo = DesignSystemRefRepository(db, org_id=current_user.org_id)
    ds = await ds_repo.get_by_id(ds_id)
    if ds is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Design system not found"
        )
    await ds_repo.delete(ds)
    logger.info("design_system_deleted", ds_id=str(ds_id))
