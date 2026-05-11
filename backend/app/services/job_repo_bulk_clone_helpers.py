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

"""Per-item helpers for :mod:`app.services.job_repo_bulk_clone`.

Split out so the orchestrating handler stays under the file-size cap.
Each function here is a leaf — they never call back into the
orchestrator and never touch the job-queue store directly except via
``update_job``.
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.repositories.tracked_repository import TrackedRepoRepository
from app.schemas.jobs import (
    BulkOnboardItemProgress,
    BulkOnboardItemState,
    BulkOnboardJobPayload,
)
from app.services.github_install_repos import compose_app_clone_url
from app.services.job_queue import update_job
from app.services.repo_cloner import _sanitize, clone_or_update

logger = structlog.get_logger(__name__)

# Progress band: see job_repo_bulk_clone for the rationale on these
# numbers. Re-declared here so this module stands alone.
JOB_PROGRESS_BASE_PCT = 5
JOB_PROGRESS_PER_ITEM_RANGE_PCT = 90

DbFactory = async_sessionmaker[AsyncSession]


def progress_pct(completed: int, total: int) -> int:
    """Map a ``completed`` count to the 5–95 progress band."""
    if total <= 0:
        return JOB_PROGRESS_BASE_PCT
    fraction = completed / total
    return JOB_PROGRESS_BASE_PCT + int(round(JOB_PROGRESS_PER_ITEM_RANGE_PCT * fraction))


def publish_progress(
    job_id: str,
    payload: BulkOnboardJobPayload,
    *,
    completed: int,
    total: int,
    message: str,
) -> None:
    """Push the current items list + bar position over the job WebSocket."""
    update_job(
        job_id,
        status_message=message,
        progress_pct=progress_pct(completed, total),
        result=payload.model_dump(by_alias=True, mode="json"),
    )


async def process_one_item(
    *,
    item: BulkOnboardItemProgress,
    token: str,
    org_id: uuid.UUID,
    org_slug: str,
    db_factory: DbFactory,
) -> None:
    """Clone + upsert a single repo. Mutates ``item`` in place; never raises.

    Uses its OWN session — never the caller's — so concurrent items
    don't share a session (asyncpg connections aren't safe to multiplex
    across coroutines).
    """
    clone_url = compose_app_clone_url(token, item.full_name)
    try:
        result = await clone_or_update(
            url=clone_url,
            org_slug=org_slug,
            branch=item.main_branch,
        )
    except Exception as exc:
        item.status = BulkOnboardItemState.ERROR
        item.error = _sanitize(str(exc), token)
        logger.warning(
            "bulk_onboard_clone_raised",
            full_name=item.full_name,
            error=item.error,
        )
        return

    if not result.success or not result.path:
        item.status = BulkOnboardItemState.ERROR
        item.error = _sanitize(result.error or "Clone failed.", token)
        logger.warning(
            "bulk_onboard_clone_failed",
            full_name=item.full_name,
            error=item.error,
        )
        return

    repo_path = Path(result.path).resolve()
    try:
        async with db_factory() as db:
            repo_repo = TrackedRepoRepository(db, org_id=org_id)
            repo = await repo_repo.upsert_for_github_repo(
                github_full_name=item.full_name,
                path=str(repo_path),
                name=repo_path.name,
            )
            await repo_repo.set_onboard_metadata(
                repo,
                github_full_name=item.full_name,
                main_branch=item.main_branch,
                develop_branch=item.develop_branch,
                uat_branch=item.uat_branch,
            )
            item.repo_id = repo.id
            await db.commit()
    except Exception as exc:
        item.status = BulkOnboardItemState.ERROR
        item.error = _sanitize(str(exc), token)
        logger.exception(
            "bulk_onboard_persist_failed",
            full_name=item.full_name,
        )
        return

    item.status = BulkOnboardItemState.DONE
    logger.info(
        "bulk_onboard_item_done",
        full_name=item.full_name,
        repo_id=str(item.repo_id),
    )


async def run_with_progress(
    *,
    job_id: str,
    payload: BulkOnboardJobPayload,
    item: BulkOnboardItemProgress,
    token: str,
    org_slug: str,
    db_factory: DbFactory,
    semaphore: asyncio.Semaphore,
    counter: dict[str, int],
    total: int,
) -> None:
    """Run one item under the concurrency semaphore + emit progress events."""
    async with semaphore:
        item.status = BulkOnboardItemState.CLONING
        publish_progress(
            job_id,
            payload,
            completed=counter["done"],
            total=total,
            message=f"Cloning {item.full_name}...",
        )

        await process_one_item(
            item=item,
            token=token,
            org_id=payload.org_id,
            org_slug=org_slug,
            db_factory=db_factory,
        )

        counter["done"] += 1
        publish_progress(
            job_id,
            payload,
            completed=counter["done"],
            total=total,
            message=f"{counter['done']}/{total} repos processed",
        )


def summarise(
    payload: BulkOnboardJobPayload,
    scan_id: uuid.UUID | None,
    *,
    scan_ids: list[uuid.UUID] | None = None,
) -> dict[str, Any]:
    """Build the terminal job-result dict for a finished bulk-onboard run.

    The ``scan_id`` (singular) field is retained for back-compat with
    any existing consumer of the bulk-onboard job result; bulk runs
    that batch their scans now also expose the full ordered list under
    ``scan_ids``.
    """
    succeeded = [it.full_name for it in payload.items if it.status is BulkOnboardItemState.DONE]
    failed = [
        {"full_name": it.full_name, "error": it.error or "Unknown error."}
        for it in payload.items
        if it.status is BulkOnboardItemState.ERROR
    ]
    serialised_scan_ids: list[str] = (
        [str(sid) for sid in scan_ids] if scan_ids else ([str(scan_id)] if scan_id else [])
    )
    return {
        "items": [it.model_dump(by_alias=True, mode="json") for it in payload.items],
        "scan_id": str(scan_id) if scan_id else None,
        "scan_ids": serialised_scan_ids,
        "succeeded": succeeded,
        "failed": failed,
    }
