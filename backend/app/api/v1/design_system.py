"""Design system management endpoints."""

import uuid
from pathlib import Path

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
    DesignSystemUpdateContent,
)
from app.schemas.jobs import DesignExtractJobPayload, JobCreatedResponse
from app.services.job_queue import JOB_DESIGN_EXTRACT, create_job

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["design-systems"])


@router.get(
    "/",
    response_model=list[DesignSystemRead],
    dependencies=[Depends(require_permissions("settings:view"))],
)
async def list_design_systems(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
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
) -> dict:
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
    # Return as dict with repo_name
    items = await repo.list_with_repo_names()
    for item in items:
        if item["id"] == ds_id:
            return item
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Design system not found")


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

    payload = DesignExtractJobPayload(
        org_id=str(current_user.org_id),
        repo_id=str(body.repo_id),
        repo_path=str(repo_path),
        is_default=body.is_default,
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
async def update_design_system_content(
    ds_id: uuid.UUID,
    body: DesignSystemUpdateContent,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Manually update the content of a design system.

    Args:
        ds_id: The design system UUID.
        body: Updated content.
        current_user: The authenticated user.
        db: The async database session.

    Returns:
        The updated design system entry.
    """
    ds_repo = DesignSystemRefRepository(db, org_id=current_user.org_id)
    ds = await ds_repo.get_by_id(ds_id)
    if ds is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Design system not found"
        )

    ds.content = body.content
    await db.flush()
    await db.refresh(ds)

    logger.info("design_system_content_updated", ds_id=str(ds_id))

    items = await ds_repo.list_with_repo_names()
    for item in items:
        if item["id"] == ds_id:
            return item

    return {
        "id": ds.id,
        "org_id": ds.org_id,
        "repo_id": ds.repo_id,
        "repo_name": None,
        "is_default": ds.is_default,
        "content": ds.content,
        "source_hash": ds.source_hash,
        "extracted_at": ds.extracted_at,
        "created_at": ds.created_at,
        "updated_at": ds.updated_at,
    }


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
