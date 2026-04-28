# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Triage session approval queue endpoints."""

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

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
from app.services.feature_lifecycle import create_planned_feature
from app.services.slack_intake import _build_bud_content

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

    bud = BUDDocument(
        org_id=current_user.org_id,
        bud_number=next_number,
        title=session.feature_name or "Untitled Feature Request",
        status=BUDStatus.BUD,
        requirements_md=requirements_md,
        metadata_={"source": "slack_triage", "triage_session_id": str(session.id)},
    )
    await bud_repo.create(bud)

    session.bud_id = bud.id
    session.status = TriageStatus.BUD_CREATED
    await db.flush()

    # Create feature registry entry
    await create_planned_feature(db, current_user.org_id, next_number, bud.title, requirements_md)

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

    # Trigger PRD agent via the agent task system
    await create_agent_task_for_stage(
        bud, "bud", current_user.org_id, db, triggered_by=current_user.id
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
