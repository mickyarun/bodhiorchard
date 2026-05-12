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
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_activity import AgentActivityLog
from app.models.tracked_repository import TrackedRepository
from app.services.event_bus import publish

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
    """Write the DB row and publish the WebSocket event."""
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
            "repo_name": repo_name,
            "bud_number": bud_number,
            "bud_title": bud_title,
            "impacted_repo_names": [],
            "created_at": log.created_at.isoformat() if log.created_at else "",
        },
    )


_STATUS_MAP: dict[str, str] = {
    "skill_invoked": "in_progress",
    "skill_completed": "completed",
    "skill_failed": "failed",
}
