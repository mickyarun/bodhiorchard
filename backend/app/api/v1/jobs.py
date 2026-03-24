"""Job status polling endpoint."""

import structlog
from fastapi import APIRouter, Depends, HTTPException, status

from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.jobs import JobStatusRead
from app.services.job_queue import get_job

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["jobs"])


@router.get(
    "/{job_id}/status",
    response_model=JobStatusRead,
)
async def get_job_status(
    job_id: str,
    current_user: User = Depends(get_current_user),
) -> JobStatusRead:
    """Poll the status of an async job.

    Args:
        job_id: The job UUID returned by the dispatch endpoint.
        current_user: The authenticated user.

    Returns:
        Current job status with progress and optional result.
    """
    job = get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )
    return job
