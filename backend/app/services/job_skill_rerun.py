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

"""Background handler for ``JOB_SKILL_RERUN``.

The synchronous skills-rerun endpoint pinned an HTTP request open for
minutes on real-world orgs (20 repos, deep history) — long enough for
client-side axios timeouts and any reverse-proxy idle window to cut the
connection mid-walk. This handler runs the same wipe-and-recompute
inside a worker task so the request returns immediately with a job id
and the UI polls progress via ``useJobSocket``.
"""

from __future__ import annotations

from typing import Any

import structlog

from app.database import AsyncSessionLocal
from app.repositories.organization import OrganizationRepository
from app.repositories.tracked_repository import TrackedRepoRepository
from app.schemas.jobs import JobState, SkillRerunJobPayload
from app.services.job_queue import update_job
from app.services.skill_rerun import rerun_skill_profiles

logger = structlog.get_logger(__name__)


async def handle_skill_rerun_job(job_id: str, raw_payload: dict[str, Any]) -> None:
    """Wipe and recompute ``skill_profiles`` for one org in the background.

    Owns the DB session so the request handler can return immediately.
    Progress reporting is coarse — one status message per repo plus the
    final summary — because the operation rarely exceeds a few minutes
    and a per-commit progress feed would dominate the WebSocket traffic.
    """
    payload = SkillRerunJobPayload(**raw_payload)

    update_job(
        job_id,
        state=JobState.RUNNING,
        status_message="Loading repositories…",
        progress_pct=2,
    )

    async with AsyncSessionLocal() as db:
        org = await OrganizationRepository(db).get_by_id(payload.org_id)
        if org is None:
            update_job(
                job_id,
                state=JobState.FAILED,
                error="Organization not found.",
                status_message="Failed",
            )
            return

        repos = await TrackedRepoRepository(db, org_id=payload.org_id).list_active()
        total = len(repos) or 1

        async def on_repo_done(name: str, idx: int) -> None:
            # Progress reserves 5% for setup and the final commit; the
            # remaining 90% is divided evenly across repos so the bar
            # advances monotonically even when a small repo finishes
            # right after a huge one.
            pct = 5 + int(90 * (idx + 1) / total)
            update_job(
                job_id,
                status_message=f"Walked {idx + 1}/{total}: {name}",
                progress_pct=pct,
            )

        try:
            result = await rerun_skill_profiles(
                db,
                payload.org_id,
                wipe=payload.wipe,
                on_repo_done=on_repo_done,
            )
            await db.commit()
        except Exception as exc:
            logger.exception("skill_rerun_job_failed", job_id=job_id)
            update_job(
                job_id,
                state=JobState.FAILED,
                error=str(exc),
                status_message="Failed",
            )
            return

    result_payload = {
        "profilesDeleted": result.profiles_deleted,
        "profilesUpserted": result.profiles_upserted,
        "unmatchedEmails": result.unmatched_emails,
        "reposWalked": result.repos_walked,
    }
    update_job(
        job_id,
        state=JobState.COMPLETED,
        status_message=(
            f"Wiped {result.profiles_deleted}, upserted {result.profiles_upserted} "
            f"across {result.repos_walked} repo(s)"
        ),
        progress_pct=100,
        result=result_payload,
    )
    logger.info(
        "skill_rerun_job_done",
        job_id=job_id,
        org_id=str(payload.org_id),
        by=payload.requested_by_email,
        profiles_deleted=result.profiles_deleted,
        profiles_upserted=result.profiles_upserted,
        repos_walked=result.repos_walked,
        unmatched_emails=result.unmatched_emails,
    )
