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

"""Centralized agent activity logging with WebSocket publish.

Replaces the duplicated db.add(AgentActivityLog) + publish() pattern
across bud_agent_handler, job_chat, job_design, and job_agents.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_activity import AgentActivityLog
from app.models.tracked_repository import TrackedRepository
from app.repositories.agent_activity import list_orphan_phase_workers
from app.repositories.bud import list_basic_info_by_ids
from app.services.event_bus import publish

# Skill slugs the dev-mode chain emits. Centralised here so both the
# emitter (bud_development, bud_assignment) and the startup reconciler
# stay in sync — adding a new phase worker requires touching exactly one
# list.
PHASE_WORKER_SLUGS: list[str] = ["phase_assigner", "pert_estimator"]

logger = structlog.get_logger(__name__)


async def log_agent_activity(
    db: AsyncSession | None,
    *,
    org_id: uuid.UUID,
    event_type: str,
    skill_slug: str,
    message: str,
    bud_id: uuid.UUID | None = None,
    skill_id: uuid.UUID | None = None,
    task_id: uuid.UUID | None = None,
    repo_id: uuid.UUID | None = None,
    metadata_: dict[str, Any] | None = None,
    bud_number: int | None = None,
    bud_title: str | None = None,
) -> None:
    """Create an AgentActivityLog entry and publish to WebSocket.

    Args:
        db: Existing session to use. If None, creates a new session
            (use for error handlers after rollback).
        org_id: Organization UUID.
        event_type: "skill_invoked", "skill_completed", or "skill_failed".
        skill_slug: Agent skill identifier (e.g. "designer", "triage").
        message: Human-readable event description.
        bud_id: Optional BUD link.
        skill_id: Optional FK to agent_skills.
        task_id: Optional FK to bud_agent_tasks.
        repo_id: Optional FK to tracked_repositories.
        metadata_: Optional JSONB metadata.
        bud_number: Optional BUD number for publish payload.
        bud_title: Optional BUD title for publish payload.
    """
    status = _STATUS_MAP.get(event_type, "in_progress")

    if db is not None:
        await _write_and_publish(
            db,
            org_id=org_id,
            event_type=event_type,
            status=status,
            skill_slug=skill_slug,
            message=message,
            bud_id=bud_id,
            skill_id=skill_id,
            task_id=task_id,
            repo_id=repo_id,
            metadata_=metadata_,
            bud_number=bud_number,
            bud_title=bud_title,
        )
    else:
        from app.database import AsyncSessionLocal

        async with AsyncSessionLocal() as fresh_db:
            await _write_and_publish(
                fresh_db,
                org_id=org_id,
                event_type=event_type,
                status=status,
                skill_slug=skill_slug,
                message=message,
                bud_id=bud_id,
                skill_id=skill_id,
                task_id=task_id,
                repo_id=repo_id,
                metadata_=metadata_,
                bud_number=bud_number,
                bud_title=bud_title,
            )
            await fresh_db.commit()


async def _write_and_publish(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    event_type: str,
    status: str,
    skill_slug: str,
    message: str,
    bud_id: uuid.UUID | None,
    skill_id: uuid.UUID | None,
    task_id: uuid.UUID | None,
    repo_id: uuid.UUID | None,
    metadata_: dict[str, Any] | None,
    bud_number: int | None,
    bud_title: str | None,
) -> None:
    """Write the DB row and publish the WebSocket event.

    ``created_at`` is set Python-side rather than via the column's
    ``server_default=func.now()``. Postgres ``now()`` returns the
    transaction-start time, which means consecutive lifecycle events
    written in the same transaction (e.g. ``auto_assign_for_phase``
    writing ``skill_invoked`` then ``skill_completed`` on either side
    of a 10-second LLM call) tie on the microsecond — and
    ``get_active_phase_worker``'s ``func.max(created_at)`` then can't
    distinguish them, leaving the progress banner forever stuck on the
    invoked row. Using ``datetime.now`` resolves each call to wall
    time, which advances within a transaction.
    """
    now = datetime.now(UTC)
    log = AgentActivityLog(
        org_id=org_id,
        skill_id=skill_id,
        task_id=task_id,
        bud_id=bud_id,
        repo_id=repo_id,
        event_type=event_type,
        status=status,
        message=message[:2000] if message else None,
        source="backend",
        skill_slug=skill_slug,
        metadata_=metadata_,
        created_at=now,
        updated_at=now,
    )
    db.add(log)
    await db.flush()

    # Resolve repo_name for the publish payload
    repo_name: str | None = None
    if repo_id:
        row = await db.execute(
            select(TrackedRepository.name).where(TrackedRepository.id == repo_id),
        )
        repo_name = row.scalar_one_or_none()

    logger.info(
        "agent_activity_publish",
        topic=f"agent_activity:{org_id}",
        event_type=event_type,
        task_id=str(task_id) if task_id else None,
    )
    publish(
        f"agent_activity:{org_id}",
        {
            "event_type": event_type,
            "status": status,
            "message": log.message,
            "skill_slug": skill_slug,
            "actor_name": skill_slug,
            "task_id": str(task_id) if task_id else None,
            "bud_id": str(bud_id) if bud_id else None,
            "repo_name": repo_name,
            "bud_number": bud_number,
            "bud_title": bud_title,
            "impacted_repo_names": [],
            "created_at": log.created_at.isoformat() if log.created_at else "",
            "metadata": metadata_,
        },
    )


_STATUS_MAP: dict[str, str] = {
    "skill_invoked": "in_progress",
    "skill_completed": "completed",
    "skill_failed": "failed",
}


async def reconcile_orphan_phase_workers(db: AsyncSession) -> int:
    """Emit ``skill_failed`` for every phase-worker still marked in-flight.

    Called once on startup to recover from a backend crash or restart that
    happened mid-chain. Mirrors ``recover_stuck_agent_tasks`` in
    ``bud_agent_task.py`` for synthetic skills that don't have a
    ``BUDAgentTask`` row.

    For each orphan ``(org_id, bud_id, skill_slug)`` whose latest
    lifecycle event is ``skill_invoked``:
      1. Look up ``bud_number`` / ``bud_title`` so the published banner
         copy matches what the live event carried.
      2. Call ``log_agent_activity`` with ``event_type='skill_failed'``
         and ``metadata.reason='server_restart'``. The publish on
         ``agent_activity:{org_id}`` decrements the live banner's
         in-flight counter; the new audit row makes
         ``get_active_phase_worker`` return ``None`` on the next mount.
      3. Each emit uses its own fresh session (db=None) so a single
         broken row can't poison the whole recovery loop.

    Returns the number of orphans reconciled.
    """
    orphans = await list_orphan_phase_workers(db, PHASE_WORKER_SLUGS)
    if not orphans:
        return 0

    bud_ids = {row.bud_id for row in orphans if row.bud_id is not None}
    bud_info = await list_basic_info_by_ids(db, bud_ids)

    reconciled = 0
    for row in orphans:
        if row.bud_id is None or row.skill_slug is None:
            continue
        info = bud_info.get(row.bud_id)
        try:
            await log_agent_activity(
                None,
                org_id=row.org_id,
                event_type="skill_failed",
                skill_slug=row.skill_slug,
                message="Server restarted while task was in progress",
                bud_id=row.bud_id,
                bud_number=info[0] if info else None,
                bud_title=info[1] if info else None,
                metadata_={"reason": "server_restart"},
            )
            reconciled += 1
        except Exception:
            logger.warning(
                "phase_worker_recovery_emit_failed",
                bud_id=str(row.bud_id),
                skill_slug=row.skill_slug,
                exc_info=True,
            )
    return reconciled
