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

"""Triage session approval queue endpoints."""

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.skill_mapping import BUD_STAGE_AGENT_TYPE
from app.core.deps import get_current_user, get_db, require_permissions
from app.core.encryption import decrypt_secret
from app.models.bud import BUDDocument, BUDStatus
from app.models.organization import Organization
from app.models.triage_session import TriageSession, TriageStatus
from app.models.user import User
from app.repositories.bud import BUDRepository
from app.repositories.organization import OrganizationRepository
from app.repositories.triage_session import TriageSessionRepository
from app.repositories.user import UserRepository
from app.schemas.triage_session import TriageApprovalRequest, TriageSessionRead
from app.services import slack_client
from app.services.bud_agent_trigger import create_agent_task_for_stage
from app.services.bud_assignment import auto_assign_for_phase
from app.services.bud_timeline import record_event
from app.services.embedding_service import embedding_service
from app.services.feature_lifecycle import create_planned_feature
from app.services.slack_intake import _build_bud_content, normalize_triage_priority

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["triage"])


async def _get_org(user: User, db: AsyncSession) -> Organization:
    """Resolve the user's organization."""
    org = await OrganizationRepository(db).get_by_id(user.org_id)
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    return org


@router.get(
    "/",
    response_model=list[TriageSessionRead],
    dependencies=[Depends(require_permissions("backlog:approve"))],
)
async def list_triage_sessions(
    status_filter: str | None = Query("awaiting_pm", alias="status"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[TriageSessionRead]:
    """List triage sessions for the current user's organization.

    Args:
        status_filter: Optional status to filter by (default: awaiting_pm).
        current_user: The authenticated user.
        db: The async database session.

    Returns:
        A list of triage sessions with resolved requester names.
    """
    if status_filter:
        valid_statuses = {s.value for s in TriageStatus}
        if status_filter not in valid_statuses:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status: {status_filter}",
            )

    repo = TriageSessionRepository(db, org_id=current_user.org_id)
    sessions = await repo.list_by_status(status_filter)

    # Resolve Slack IDs to user display names from the users table
    slack_ids = {s.requester_slack_id for s in sessions if s.requester_slack_id}
    slack_to_name = await _resolve_slack_names(db, current_user.org_id, slack_ids)

    results: list[TriageSessionRead] = []
    for session in sessions:
        data = TriageSessionRead.model_validate(session)
        data.requester_display_name = slack_to_name.get(session.requester_slack_id)
        results.append(data)

    return results


async def _resolve_slack_names(
    db: AsyncSession, org_id: uuid.UUID, slack_ids: set[str]
) -> dict[str, str]:
    """Look up Bodhiorchard user names by their Slack IDs.

    Args:
        db: Async database session.
        org_id: Organization UUID for scoping.
        slack_ids: Set of Slack user IDs to resolve.

    Returns:
        Mapping of slack_id → user display name.
    """
    return await UserRepository(db).get_slack_id_to_name(org_id, slack_ids)


@router.post(
    "/{session_id}/approve",
    response_model=TriageSessionRead,
    dependencies=[Depends(require_permissions("backlog:approve"))],
)
async def approve_triage_session(
    session_id: uuid.UUID,
    body: TriageApprovalRequest | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TriageSessionRead:
    """Approve a triage session — creates a BUD and triggers the PRD agent.

    Args:
        session_id: The triage session UUID.
        body: Optional approval notes.
        current_user: The authenticated user.
        db: The async database session.

    Returns:
        The updated triage session.

    Raises:
        HTTPException: If the session is not found or not in awaiting_pm status.
    """
    repo = TriageSessionRepository(db, org_id=current_user.org_id)
    session = await repo.get_by_id(session_id)

    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Triage session not found"
        )

    if session.status != TriageStatus.AWAITING_PM:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Session is in '{session.status}' status, not awaiting approval",
        )

    # Create BUD
    bud_repo = BUDRepository(db, org_id=current_user.org_id)
    next_number = await bud_repo.next_bud_number()

    requirements_md = _build_bud_content(session)

    # Default every agent-running stage to ON so design / tech_arch / testing
    # agents fire on later transitions. Without this the column defaults to
    # NULL and ``should_auto_generate_phase`` skips every downstream stage —
    # the BUD/PRD agent at the end of this handler is the only thing that
    # would ever run. Matches the manual create-BUD dialog (BUDBoard.vue),
    # where each switch starts ON for the same reason.
    auto_generate_phases = {stage.value: True for stage in BUD_STAGE_AGENT_TYPE}

    bud = BUDDocument(
        org_id=current_user.org_id,
        bud_number=next_number,
        title=session.feature_name or "Untitled Feature Request",
        status=BUDStatus.BUD,
        priority=normalize_triage_priority(session.priority),
        requirements_md=requirements_md,
        metadata_={"source": "slack_triage", "triage_session_id": str(session.id)},
        auto_generate_phases=auto_generate_phases,
    )
    await bud_repo.create(bud)

    session.bud_id = bud.id
    session.status = TriageStatus.BUD_CREATED
    await db.flush()

    # Generate embedding so the bug linker can match incoming bugs to this BUD
    # via pgvector cosine distance (0.40 threshold). Without this, triage-born
    # BUDs are invisible to bug auto-linking. Mirrors the manual create-BUD
    # path. Best-effort: a failure here must not block the approval flow.
    try:
        embed_text = bud.title
        if requirements_md:
            embed_text = f"{bud.title} {requirements_md[:500]}"
        bud.embedding = await embedding_service.embed(embed_text)
        await db.flush()
    except Exception:
        logger.warning("bud_embedding_failed", bud_number=next_number, exc_info=True)

    # Create feature registry entry
    await create_planned_feature(db, current_user.org_id, next_number, bud.title, requirements_md)

    # Timeline + auto-assign — same side effects the manual create-BUD path
    # runs. Auto-assignment uses the priority-aware smart routing introduced
    # on this branch; without this call, triage-born BUDs land unassigned.
    await record_event(
        db,
        current_user.org_id,
        bud.id,
        "created",
        actor_id=current_user.id,
        actor_name=current_user.name,
        detail={"source": "slack_triage", "triage_session_id": str(session.id)},
    )
    await auto_assign_for_phase(
        db,
        current_user.org_id,
        bud,
        BUDStatus.BUD,
        actor_id=current_user.id,
        actor_name=current_user.name,
    )

    bud_ref = f"BUD-{next_number:03d}"
    logger.info(
        "triage_approved_via_ui",
        session_id=str(session.id),
        bud_ref=bud_ref,
        approver=current_user.email,
    )

    # Post Slack confirmation and dispatch PRD agent via job queue
    org = await _get_org(current_user, db)
    bot_token = _get_bot_token(org)

    if bot_token:
        await slack_client.chat_post_message(
            bot_token,
            session.slack_channel,
            f"✅ *{bud_ref}* created: *{bud.title}*\nApproved by {current_user.name}.",
            thread_ts=session.thread_ts,
        )

    # Trigger PRD agent via the agent task system. ``force=True`` because
    # ``_build_bud_content`` has already populated ``requirements_md`` with
    # the structured Slack-triage summary — without the override, the
    # trigger's "skip if output section has content" guard fires and the
    # PRD agent never runs, leaving the BUD with raw triage text instead
    # of a refined PRD. Mirrors the manual create-BUD path in bud.py.
    await create_agent_task_for_stage(
        bud,
        "bud",
        current_user.org_id,
        db,
        triggered_by=current_user.id,
        force=True,
    )

    return await _session_to_read(session, current_user, db)


@router.post(
    "/{session_id}/reject",
    response_model=TriageSessionRead,
    dependencies=[Depends(require_permissions("backlog:approve"))],
)
async def reject_triage_session(
    session_id: uuid.UUID,
    body: TriageApprovalRequest | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TriageSessionRead:
    """Reject a triage session.

    Args:
        session_id: The triage session UUID.
        body: Optional rejection notes.
        current_user: The authenticated user.
        db: The async database session.

    Returns:
        The updated triage session.

    Raises:
        HTTPException: If the session is not found or not in awaiting_pm status.
    """
    repo = TriageSessionRepository(db, org_id=current_user.org_id)
    session = await repo.get_by_id(session_id)

    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Triage session not found"
        )

    if session.status != TriageStatus.AWAITING_PM:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Session is in '{session.status}' status, not awaiting approval",
        )

    session.status = TriageStatus.REJECTED
    await db.flush()

    logger.info(
        "triage_rejected_via_ui",
        session_id=str(session.id),
        rejector=current_user.email,
    )

    # Post Slack notification
    org = await _get_org(current_user, db)
    bot_token = _get_bot_token(org)

    if bot_token:
        await slack_client.chat_post_message(
            bot_token,
            session.slack_channel,
            f"❌ Feature request declined by {current_user.name}.",
            thread_ts=session.thread_ts,
        )

    return await _session_to_read(session, current_user, db)


async def _session_to_read(
    session: TriageSession, user: User, db: AsyncSession
) -> TriageSessionRead:
    """Convert a TriageSession ORM object to the response schema."""
    await db.refresh(session)
    data = TriageSessionRead.model_validate(session)
    if session.requester_slack_id:
        names = await _resolve_slack_names(db, user.org_id, {session.requester_slack_id})
        data.requester_display_name = names.get(session.requester_slack_id)
    return data


def _get_bot_token(org: Organization) -> str | None:
    """Decrypt and return the Slack bot token from the org, or None."""
    if not org.slack_bot_token:
        return None
    return decrypt_secret(org.slack_bot_token)
