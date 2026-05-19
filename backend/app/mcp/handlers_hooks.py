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

"""Handlers for Claude Code hook activity reports.

Processes all activity events from Claude Code hooks and git hooks,
sent via POST /mcp/dev-activity with MCP token auth. All events are
stored in a single unified dev_activity_logs table.
"""

import asyncio
import os
import re
import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.mcp.auth import MCPAuthResult
from app.models.dev_activity import DevActivityLog
from app.repositories.bud import BUDRepository
from app.repositories.dev_activity import DevActivityLogRepository
from app.repositories.tracked_repository import TrackedRepoRepository
from app.schemas.dev_activity import DevActivityHookRequest, DevActivityHookResponse
from app.services.colyseus_bridge import publish_to_colyseus
from app.services.event_bus import publish
from app.services.user_resolution import resolve_user_by_email
from app.services.xp_service import check_and_award_streak

logger = structlog.get_logger(__name__)

_BUD_BRANCH_RE = re.compile(r"^bud-(\d+)/")


async def handle_dev_activity(
    db: AsyncSession,
    auth: MCPAuthResult,
    body: DevActivityHookRequest,
) -> DevActivityHookResponse:
    """Process a Claude Code hook activity report.

    All event types go into a single DevActivityLog table. The handler:
    1. Resolves user from MCP token (or falls back to email)
    2. Resolves repo_id from repo_path
    3. Auto-detects BUD from branch name if not provided
    4. Creates a DevActivityLog entry

    Args:
        db: The async database session.
        auth: The authenticated org + user from MCP token.
        body: The validated hook request.

    Returns:
        Response indicating success and resolution details.
    """
    org = auth.org

    # 1. Resolve user — token first, email fallback
    user = auth.user
    token_owner_email = user.email if user else None
    resolved_via = "token" if user else "none"
    if user is None and body.author_email:
        user = await resolve_user_by_email(db, org.id, body.author_email)
        if user:
            resolved_via = "email_fallback"

    user_id = user.id if user else None
    actor_name = user.name if user else None

    # DEBUG: log the attribution resolution so we can see which user the
    # row is attributed to. The effective ROLE (for testing-tab routing)
    # is computed at READ time by joining through org_to_user → roles,
    # so there's nothing to snapshot here — just making sure the right
    # user_id lands on the row. Remove after triage.
    logger.info(
        "hook_activity_attribution",
        event_type=body.event_type,
        token_owner_email=token_owner_email,
        git_author_email=body.author_email or None,
        resolved_via=resolved_via,
        resolved_user_id=str(user_id) if user_id else None,
        resolved_actor_name=actor_name,
        branch=body.branch or None,
        repo_path=body.repo_path or None,
    )

    # 2. Resolve repo_id from repo_path
    repo_id = await _resolve_repo_id(db, org.id, body.repo_path)

    # 3. Resolve BUD — from request, then from branch name
    bud_id, bud_number = await _resolve_bud(
        db,
        org.id,
        body.bud_number,
        body.branch,
    )

    # 4. Dedup: skip if this commit SHA was already recorded
    activity_repo = DevActivityLogRepository(db, org_id=org.id)
    if (
        body.event_type == "commit"
        and body.commit_sha
        and await activity_repo.commit_sha_exists(body.commit_sha)
    ):
        logger.debug("hook_commit_duplicate", sha=body.commit_sha[:8])
        return DevActivityHookResponse(
            success=True,
            event_type=body.event_type,
            bud_number=bud_number,
            user_resolved=user_id is not None,
        )

    # 5. Merge author_email into metadata for contributor resolution
    meta = dict(body.metadata) if body.metadata else {}
    if body.author_email:
        meta["author_email"] = body.author_email

    # 6. Create unified activity log entry
    log = DevActivityLog(
        org_id=org.id,
        bud_id=bud_id,
        user_id=user_id,
        repo_id=repo_id,
        session_id=body.session_id or None,
        event_type=body.event_type,
        status=_infer_status(body.event_type),
        message=body.message[:2000] if body.message else None,
        source="claude_hook",
        actor_name=actor_name,
        branch=body.branch or None,
        commit_sha=body.commit_sha or None,
        file_path=body.file_path or None,
        files_changed=body.files_changed or None,
        # Persist the raw repo_path verbatim, even when repo_id is None
        # (i.e. the path doesn't match any tracked_repository). The BUD
        # testing tab uses this to surface "untracked" repos with an
        # "Add as tracked" CTA. Truncate defensively to fit the column.
        repo_path=(body.repo_path[:1000] if body.repo_path else None),
        metadata_=meta or None,
    )
    db.add(log)
    await db.flush()
    await db.refresh(log)

    # Backfill prior session events that arrived without a bud_id
    if bud_id and body.session_id:
        await activity_repo.backfill_session_bud(body.session_id, bud_id)

    # Resolve repo_name for real-time payloads (same pattern as handle_agent_activity)
    _pub_repo_name: str | None = None
    if repo_id:
        _pub_repo_name = await TrackedRepoRepository(db, org_id=org.id).get_name_by_id(repo_id)

    # Publish for real-time WebSocket updates if BUD-linked
    if bud_id:
        publish(
            f"bud:{bud_id}:activity",
            {
                "id": str(log.id),
                "event_type": body.event_type,
                "status": log.status,
                "message": log.message,
                "source": "claude_hook",
                "actor_name": actor_name,
                "user_id": str(user_id) if user_id else None,
                "repo_name": _pub_repo_name,
                "file_path": body.file_path,
                "created_at": log.created_at.isoformat(),
            },
        )

    # Forward to Colyseus so the authoritative server simulation drives
    # character movement for every viewer of this org's dashboard. Detached so
    # a slow/unreachable Colyseus server cannot stall the hook request path
    # (publish_to_colyseus has a 2s internal timeout and logs its own errors).
    dev_activity_payload = {
        "id": str(log.id),
        "event_type": body.event_type,
        "status": log.status,
        "message": log.message,
        "source": "claude_hook",
        "actor_name": actor_name,
        "user_id": str(user_id) if user_id else None,
        "repo_name": _pub_repo_name,
        "file_path": body.file_path,
        "created_at": log.created_at.isoformat(),
    }
    asyncio.create_task(publish_to_colyseus(org.id, "dev_activity", dev_activity_payload))

    # Daily-streak XP only — individual commits no longer credit XP. The
    # outcome-based model awards XP at stage promotion (PR merged into a
    # tracked repo's develop / uat / main branch), split among everyone
    # who contributed to the BUD.
    if user_id:
        try:
            await check_and_award_streak(db, user_id=user_id, org_id=org.id)
        except Exception:
            logger.warning("xp_streak_award_failed", user_id=str(user_id), exc_info=True)

    logger.info(
        "hook_activity_recorded",
        event_type=body.event_type,
        bud_number=bud_number,
        user_id=str(user_id) if user_id else None,
        repo_id=str(repo_id) if repo_id else None,
    )

    return DevActivityHookResponse(
        success=True,
        event_type=body.event_type,
        bud_number=bud_number,
        user_resolved=user_id is not None,
    )


async def _resolve_repo_id(
    db: AsyncSession,
    org_id: uuid.UUID,
    repo_path: str,
) -> uuid.UUID | None:
    """Resolve a filesystem repo_path to a tracked_repositories.id.

    Exact-path match is attempted first — that works when the hook fires
    from the same machine the scan pipeline indexed (single-host dev).
    When the developer's laptop path doesn't match the server's clone
    path (the common case for remote teams talking to garden.atoa.me),
    fall back to matching by the repo's basename within the org. The
    repository lookups are org-scoped, so collisions across orgs that
    happen to use the same repo basename don't matter.
    """
    if not repo_path:
        return None
    repo_repo = TrackedRepoRepository(db, org_id=org_id)
    tracked = await repo_repo.get_by_path(repo_path)
    if tracked:
        return tracked.id
    basename = os.path.basename(repo_path.rstrip("/"))
    if not basename:
        return None
    tracked = await repo_repo.get_by_name(basename)
    return tracked.id if tracked else None


async def _resolve_bud(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud_number: int | None,
    branch: str,
) -> tuple[uuid.UUID | None, int | None]:
    """Resolve BUD from explicit number or branch name pattern.

    Args:
        db: The async database session.
        org_id: Organization UUID.
        bud_number: Explicit BUD number from request (if any).
        branch: Git branch name (may contain bud-NNN/ pattern).

    Returns:
        Tuple of (bud_id, bud_number) or (None, None).
    """
    bud_repo = BUDRepository(db, org_id=org_id)

    # Try explicit bud_number first
    if bud_number is not None:
        bud = await bud_repo.get_by_number(bud_number)
        if bud:
            return bud.id, bud.bud_number

    # Auto-detect from branch name: bud-001/feature → 1
    if branch:
        match = _BUD_BRANCH_RE.match(branch)
        if match:
            detected_num = int(match.group(1))
            bud = await bud_repo.get_by_number(detected_num)
            if bud:
                return bud.id, bud.bud_number

    return None, None


def _infer_status(event_type: str) -> str:
    """Infer a status from event_type for backward compat with existing UI."""
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
    }
    return status_map.get(event_type, "in_progress")
