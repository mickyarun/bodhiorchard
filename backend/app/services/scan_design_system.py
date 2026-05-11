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

"""Design-system auto-extraction trigger.

Called by the ``DESIGN_SYSTEM_EXTRACT`` phase of the scan pipeline. The
actual LLM/regex extraction runs in a background job
(``JOB_DESIGN_EXTRACT``) so the scan itself stays responsive — this
module only performs the fast "do we need to enqueue?" checks:

1. Is this a UI platform we recognise? Skip if not.
2. Are there any design-related source files? Skip if none.
3. Has the hash of those files changed since the last extraction? Skip
   if unchanged (unless the caller forces a full rescan).
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)


async def maybe_extract_design_system(
    db: AsyncSession,
    org_id: uuid.UUID,
    scan_path: str,
    tracked_repo: Any | None,
    full_rescan: bool,
) -> None:
    """Enqueue async design-system extraction if source files changed.

    Returns early and logs a debug line when the repo is not a supported
    UI platform or when the hash of discovered files matches the last
    extraction (unless ``full_rescan`` is True).

    Args:
        db: Async database session.
        org_id: Organisation UUID.
        scan_path: Path to scan. May be a worktree; used for file
            discovery + hashing only. The permanent repo path is taken
            from ``tracked_repo.path`` and passed to the job worker.
        tracked_repo: ``TrackedRepository`` model instance (or None for
            ad-hoc scans that don't have a persistent repo row).
        full_rescan: Force re-extraction even when the hash matches.
    """
    from app.repositories.design_system import DesignSystemRefRepository
    from app.services.design_system_extractor import (
        compute_hash,
        discover_design_files,
        read_discovered_files,
    )
    from app.services.platforms import UI_KINDS, detect_platform

    repo = Path(scan_path)
    platform = detect_platform(repo)
    if platform is None or platform.kind not in UI_KINDS:
        logger.debug(
            "design_system_skip_non_ui_platform",
            repo=repo.name,
            platform=platform.slug if platform else None,
        )
        return

    discovered = discover_design_files(repo, platform)
    if not discovered:
        logger.debug(
            "design_system_no_files_discovered",
            repo=repo.name,
            platform=platform.slug,
        )
        return

    repo_id = tracked_repo.id if tracked_repo and hasattr(tracked_repo, "id") else None
    if repo_id is None:
        return

    file_contents = read_discovered_files(discovered)
    source_hash = compute_hash(file_contents)

    ds_repo = DesignSystemRefRepository(db, org_id=org_id)
    existing = await ds_repo.get_for_repo(repo_id)
    if existing and existing.source_hash == source_hash and not full_rescan:
        logger.info(
            "design_system_unchanged",
            repo=repo.name,
            hash=source_hash[:12],
        )
        return

    from app.schemas.jobs import DesignExtractJobPayload
    from app.services.job_queue import JOB_DESIGN_EXTRACT, create_job, is_job_active

    if is_job_active(JOB_DESIGN_EXTRACT, {"repo_id": str(repo_id)}):
        logger.info("design_extract_already_queued", repo=repo.name)
        return

    existing_default = await ds_repo.get_default()
    # Use tracked_repo.path (permanent) not scan_path (worktree, may be deleted).
    permanent_path: str = (
        tracked_repo.path
        if tracked_repo is not None and hasattr(tracked_repo, "path")
        else scan_path
    )

    job = create_job(
        JOB_DESIGN_EXTRACT,
        payload=DesignExtractJobPayload(
            org_id=str(org_id),
            repo_id=str(repo_id),
            repo_path=permanent_path,
            is_default=existing_default is None,
            platform=platform.slug,
        ).model_dump(),
    )
    logger.info(
        "design_extract_enqueued",
        repo=repo.name,
        platform=platform.slug,
        file_count=len(discovered),
        job_id=job.job_id,
    )
