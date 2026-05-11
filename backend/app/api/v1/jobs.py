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

"""Job status polling + cancellation endpoints."""

import structlog
from fastapi import APIRouter, Depends, HTTPException, status

from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.jobs import JobState, JobStatusRead
from app.services.job_queue import cancel_job, get_job

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


@router.post("/{job_id}/cancel", response_model=JobStatusRead)
async def cancel_job_endpoint(
    job_id: str,
    current_user: User = Depends(get_current_user),
) -> JobStatusRead:
    """Signal a running job to cancel.

    Pure signal — pokes the paired ``asyncio.Task`` so the worker's
    ``CancelledError`` branch fires. The worker owns terminal state
    transitions (DB rows, subprocess cleanup, WS event emission).

    For BUD agent tasks prefer the task-level endpoint at
    ``POST /v1/buds/{bud_id}/agent-tasks/{task_id}/cancel`` — it also
    handles orphan DB rows left over after a backend restart, which
    this endpoint cannot, since the in-memory job is gone.
    """
    job = get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )
    if job.state in (JobState.COMPLETED, JobState.FAILED, JobState.CANCELLED):
        return job

    cancel_job(job_id, reason=f"Cancelled by {current_user.email}")
    updated = get_job(job_id) or job
    logger.info("job_cancel_signalled", job_id=job_id, by=current_user.email)
    return updated
