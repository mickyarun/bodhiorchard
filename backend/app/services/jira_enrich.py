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

"""Batch AI enrichment for imported Jira BUDs.

Triggers the existing PRD agent on each BUD created from an import
session, one at a time with a delay to avoid overwhelming the agent
worker pool (which has only 2 workers by default).

Usage: registered as ``JOB_JIRA_ENRICH`` in the job queue, triggered
via ``POST /v1/jira/sessions/{id}/enrich``.
"""

import asyncio
import uuid
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bud import BUDDocument, BUDStatus
from app.repositories.jira_import import JiraIssueBudMapRepository
from app.services.job_queue import JobState, update_job

logger = structlog.get_logger(__name__)

# Delay between triggering individual BUD agents to avoid queue overflow.
# The BUD agent queue has maxsize=50 and 2 workers — each agent run takes
# 30-120s, so spacing at 5s keeps the queue shallow.
_INTER_BUD_DELAY_S = 5.0


async def handle_enrich_job(job_id: str, raw_payload: dict[str, Any]) -> None:
    """Trigger PRD agent on all BUDs from an import session.

    For each imported BUD:
    1. Check if requirements_md looks like raw Jira content (not yet enriched)
    2. Trigger the PRD agent via ``create_agent_task_for_stage``
    3. Wait for a short delay before next BUD
    4. Report progress via ``update_job``
    """
    org_id = uuid.UUID(raw_payload["org_id"])
    session_id = uuid.UUID(raw_payload["session_id"])
    triggered_by_str = raw_payload.get("triggered_by")
    triggered_by = uuid.UUID(triggered_by_str) if triggered_by_str else None

    from app.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        try:
            update_job(job_id, state=JobState.RUNNING, status_message="Loading imported BUDs...")

            # Find all BUDs from this import session
            bud_ids = await _get_imported_bud_ids(db, org_id, session_id)
            total = len(bud_ids)

            if total == 0:
                update_job(
                    job_id,
                    state=JobState.COMPLETED,
                    status_message="No BUDs to enrich",
                    progress_pct=100,
                )
                return

            enriched = 0
            skipped = 0
            failed = 0

            for i, bud_id in enumerate(bud_ids):
                try:
                    result = await _enrich_single_bud(db, org_id, bud_id, triggered_by)
                    if result == "triggered":
                        enriched += 1
                    else:
                        skipped += 1
                except Exception as exc:
                    failed += 1
                    logger.warning("enrich_bud_failed", bud_id=str(bud_id), error=str(exc))

                pct = int(100 * (i + 1) / total)
                update_job(
                    job_id,
                    status_message=(
                        f"Enriching: {i + 1}/{total} "
                        f"({enriched} triggered, {skipped} skipped, {failed} failed)"
                    ),
                    progress_pct=pct,
                )

                # Delay between agents to avoid queue overflow
                if i < total - 1:
                    await asyncio.sleep(_INTER_BUD_DELAY_S)

            update_job(
                job_id,
                state=JobState.COMPLETED,
                status_message=f"Done: {enriched} enriched, {skipped} skipped, {failed} failed",
                progress_pct=100,
                result={
                    "total": total,
                    "enriched": enriched,
                    "skipped": skipped,
                    "failed": failed,
                },
            )

        except Exception as exc:
            logger.exception("jira_enrich_job_failed", session_id=str(session_id))
            update_job(
                job_id,
                state=JobState.FAILED,
                error=str(exc)[:500],
                status_message="Enrichment failed",
            )


async def _get_imported_bud_ids(
    db: AsyncSession,
    org_id: uuid.UUID,
    session_id: uuid.UUID,
) -> list[uuid.UUID]:
    """Get all BUD IDs created from an import session."""
    return await JiraIssueBudMapRepository(db, org_id=org_id).list_imported_bud_ids_for_session(
        session_id
    )


async def _enrich_single_bud(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud_id: uuid.UUID,
    triggered_by: uuid.UUID | None,
) -> str:
    """Trigger PRD agent on a single BUD.

    Returns:
        "triggered" if agent was started, "skipped" if already enriched or active.
    """
    bud = await db.get(BUDDocument, bud_id)
    if not bud or bud.org_id != org_id:
        return "skipped"

    # Only enrich BUDs still in initial "bud" status
    if bud.status != BUDStatus.BUD:
        return "skipped"

    from app.services.bud_agent_trigger import create_agent_task_for_stage

    await create_agent_task_for_stage(
        bud,
        BUDStatus.BUD,
        org_id,
        db,
        triggered_by=triggered_by,
        force=True,  # Force re-run even though requirements_md has content
    )
    return "triggered"
