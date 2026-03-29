"""Handlers for agent activity reports.

Processes activity events from two sources:
1. Claude Code hooks in tracked repos (when BODHIGROVE_AGENT_SKILL_SLUG is set)
2. Backend direct logging (skill lifecycle events)

All events are stored in agent_activity_logs, linked to agent_skills.
"""

import contextlib
import uuid

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.mcp.auth import MCPAuthResult
from app.mcp.handlers_hooks import _resolve_bud, _resolve_repo_id
from app.models.agent_activity import AgentActivityLog
from app.models.agent_skill import AgentSkill
from app.models.tracked_repository import TrackedRepository
from app.schemas.agent_activity import (
    AgentActivityHookRequest,
    AgentActivityHookResponse,
)
from app.services.event_bus import publish

logger = structlog.get_logger(__name__)


async def handle_agent_activity(
    db: AsyncSession,
    auth: MCPAuthResult,
    body: AgentActivityHookRequest,
) -> AgentActivityHookResponse:
    """Process an agent activity report.

    Resolves skill_id from skill_slug, user from auth, repo from path,
    and BUD from branch name. Creates an AgentActivityLog entry.

    Args:
        db: The async database session.
        auth: The authenticated org + user from MCP token.
        body: The validated activity request.

    Returns:
        Response indicating success and resolution details.
    """
    org = auth.org

    # 1. Resolve user — token first, email fallback
    user = auth.user
    if user is None and body.author_email:
        from app.services.user_resolution import resolve_user_by_email

        user = await resolve_user_by_email(db, org.id, body.author_email)

    user_id = user.id if user else None
    actor_name = user.name if user else None

    # 2. Resolve repo_id from repo_path
    repo_id = await _resolve_repo_id(db, org.id, body.repo_path)

    # 3. Resolve BUD — from request, then from branch name
    bud_id, bud_number = await _resolve_bud(
        db, org.id, body.bud_number, body.branch,
    )

    # 4. Resolve skill_id from skill_slug
    skill_id = await _resolve_skill_id(db, org.id, body.skill_slug)

    # 5. Resolve task_id if provided
    task_id: uuid.UUID | None = None
    if body.agent_task_id:
        with contextlib.suppress(ValueError):
            task_id = uuid.UUID(body.agent_task_id)

    # 6. Dedup: skip if this commit SHA was already recorded
    if body.event_type == "commit" and body.commit_sha:
        dup_stmt = select(AgentActivityLog.id).where(
            AgentActivityLog.org_id == org.id,
            AgentActivityLog.event_type == "commit",
            AgentActivityLog.commit_sha == body.commit_sha,
        ).limit(1)
        dup = await db.execute(dup_stmt)
        if dup.scalar_one_or_none() is not None:
            logger.debug("agent_activity_commit_duplicate", sha=body.commit_sha[:8])
            return AgentActivityHookResponse(
                success=True,
                event_type=body.event_type,
                bud_number=bud_number,
                user_resolved=user_id is not None,
                skill_resolved=skill_id is not None,
            )

    # 7. Merge author_email into metadata
    meta = dict(body.metadata) if body.metadata else {}
    if body.author_email:
        meta["author_email"] = body.author_email

    # 8. Create agent activity log entry
    log = AgentActivityLog(
        org_id=org.id,
        skill_id=skill_id,
        task_id=task_id,
        bud_id=bud_id,
        user_id=user_id,
        repo_id=repo_id,
        session_id=body.session_id or None,
        event_type=body.event_type,
        status=_infer_status(body.event_type),
        message=body.message[:2000] if body.message else None,
        source="claude_hook",
        skill_slug=body.skill_slug or None,
        agent_type=body.agent_type or None,
        actor_name=actor_name,
        branch=body.branch or None,
        commit_sha=body.commit_sha or None,
        file_path=body.file_path or None,
        files_changed=body.files_changed or None,
        metadata_=meta or None,
    )
    db.add(log)
    await db.flush()
    await db.refresh(log)

    # 9. Backfill prior session events that arrived without a bud_id
    if bud_id and body.session_id:
        await db.execute(
            update(AgentActivityLog)
            .where(
                AgentActivityLog.session_id == body.session_id,
                AgentActivityLog.org_id == org.id,
                AgentActivityLog.bud_id.is_(None),
            )
            .values(bud_id=bud_id)
        )

    # 10. Publish for real-time WebSocket updates (org-scoped for security)
    # Resolve repo_name for the payload so live-spawned robots have positioning data
    _pub_repo_name: str | None = None
    if repo_id:
        _repo_row = await db.execute(
            select(TrackedRepository.name).where(TrackedRepository.id == repo_id)
        )
        _pub_repo_name = _repo_row.scalar_one_or_none()

    publish(
        f"agent_activity:{org.id}",
        {
            "id": str(log.id),
            "event_type": body.event_type,
            "status": log.status,
            "message": log.message,
            "source": "claude_hook",
            "skill_slug": body.skill_slug,
            "actor_name": actor_name,
            "user_id": str(user_id) if user_id else None,
            "file_path": body.file_path,
            "created_at": log.created_at.isoformat(),
            "task_id": str(log.task_id) if log.task_id else None,
            "repo_name": _pub_repo_name,
            "bud_number": bud_number,
            "bud_title": None,  # not available at hook time without extra query
            "impacted_repo_names": [],  # resolved by frontend from initial data
        },
    )

    logger.info(
        "agent_activity_recorded",
        event_type=body.event_type,
        skill_slug=body.skill_slug,
        bud_number=bud_number,
        user_id=str(user_id) if user_id else None,
        repo_id=str(repo_id) if repo_id else None,
    )

    return AgentActivityHookResponse(
        success=True,
        event_type=body.event_type,
        bud_number=bud_number,
        user_resolved=user_id is not None,
        skill_resolved=skill_id is not None,
    )


async def _resolve_skill_id(
    db: AsyncSession,
    org_id: uuid.UUID,
    skill_slug: str,
) -> uuid.UUID | None:
    """Resolve a skill_slug to agent_skills.id for this org."""
    if not skill_slug:
        return None
    stmt = select(AgentSkill.id).where(
        AgentSkill.org_id == org_id,
        AgentSkill.skill_slug == skill_slug,
    ).limit(1)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


def _infer_status(event_type: str) -> str:
    """Infer a status from event_type."""
    status_map: dict[str, str] = {
        "session_start": "in_progress",
        "session_end": "completed",
        "commit": "in_progress",
        "activity_summary": "in_progress",
        "file_change": "in_progress",
        "tool_call": "in_progress",
        "tool_error": "failed",
        "api_error": "failed",
        "user_prompt": "in_progress",
        "subagent_start": "in_progress",
        "subagent_stop": "completed",
        "skill_invoked": "in_progress",
        "skill_completed": "completed",
        "skill_failed": "failed",
    }
    return status_map.get(event_type, "in_progress")
