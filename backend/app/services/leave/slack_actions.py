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

"""Approving and rejecting leave from Slack, without opening the app.

Slack signs every click; :mod:`app.services.slack_verify` has already
matched it to the org. Here the clicking Slack user is matched to an
active member of that org, and the decision goes through the same
:func:`~app.services.leave.lifecycle.decide` as the app — so the same
rules apply: only their managers or HR, never your own request, first
decision wins.
"""

import uuid
from dataclasses import dataclass
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permission_deps import PermissionSet, member_permission_set
from app.models.leave_request import LeaveStatus
from app.models.organization import Organization
from app.models.user import User
from app.repositories.user import UserRepository
from app.services.background import spawn
from app.services.leave.approvers import approvers_for, route_for
from app.services.leave.errors import LeaveError
from app.services.leave.lifecycle import decide, load_request
from app.services.leave.messages import compose_request_message
from app.services.leave.notify import stage_decision
from app.services.leave.slack_blocks import (
    APPROVE,
    NOTE_BLOCK,
    NOTE_INPUT,
    REJECT,
    REJECT_VIEW,
    reject_view,
)
from app.services.leave.slack_prompts import refresh_prompts
from app.services.slack_dm import bot_token
from app.services.slack_interactive import open_view, post_ephemeral

logger = structlog.get_logger(__name__)

OPEN_FAILED = "Slack didn't open the rejection form in time. Click Reject again."
NOT_LINKED = (
    "Your Slack account isn't linked to an active Bodhiorchard member in this workspace, "
    "so you can't decide leave from here."
)


@dataclass(frozen=True)
class Actor:
    """The member behind a Slack click, with their permissions."""

    user: User
    perms: PermissionSet


async def handle_interaction(
    db: AsyncSession, org: Organization, payload: dict[str, Any]
) -> dict[str, Any] | None:
    """Handle a verified Slack interaction; returns a response body, if any."""
    kind = payload.get("type")
    if kind == "block_actions":
        await _on_button(db, org, payload)
        return None
    view = payload.get("view") or {}
    if kind == "view_submission" and view.get("callback_id") == REJECT_VIEW:
        return await _on_reject_note(db, org, payload, view)
    return None


async def _actor(db: AsyncSession, org_id: uuid.UUID, slack_user: str) -> Actor | None:
    found = await UserRepository(db).get_by_slack_id_with_role(org_id, slack_user)
    # Same bar as signing in: active, and not waiting to replace a temporary password.
    if found is None or not found[0].is_active or found[0].must_change_password:
        return None
    perms = await member_permission_set(db, found[0].id, org_id)
    return Actor(user=found[0], perms=perms) if perms is not None else None


async def _on_button(db: AsyncSession, org: Organization, payload: dict[str, Any]) -> None:
    action = (payload.get("actions") or [{}])[0]
    action_id = action.get("action_id")
    if action_id not in (APPROVE, REJECT):
        return  # e.g. the "Open" link button
    request_id = _uuid(action.get("value"))
    slack_user = str((payload.get("user") or {}).get("id") or "")
    channel = str((payload.get("channel") or {}).get("id") or "")
    token = await bot_token(db, org.id)
    if request_id is None or not token:
        return
    actor = await _actor(db, org.id, slack_user)
    if actor is None:
        await post_ephemeral(token, channel, slack_user, NOT_LINKED)
        return
    if action_id == APPROVE:
        problem = await _decide(db, org.id, actor, request_id, approve=True, note=None)
        if problem:
            await post_ephemeral(token, channel, slack_user, problem)
        return
    problem = await _check_may_decide(db, org.id, actor, request_id)
    if problem:
        await post_ephemeral(token, channel, slack_user, problem)
        return
    request = await load_request(db, org.id, request_id)
    names = await UserRepository(db).get_names_by_ids({request.user_id})
    text = compose_request_message(
        names.get(request.user_id, "Someone"), request, auto_approved=False
    )
    if await open_view(token, str(payload.get("trigger_id") or ""), reject_view(request_id, text)):
        await post_ephemeral(token, channel, slack_user, OPEN_FAILED)


async def _on_reject_note(
    db: AsyncSession, org: Organization, payload: dict[str, Any], view: dict[str, Any]
) -> dict[str, Any] | None:
    request_id = _uuid(view.get("private_metadata"))
    values = ((view.get("state") or {}).get("values") or {}).get(NOTE_BLOCK) or {}
    note = str((values.get(NOTE_INPUT) or {}).get("value") or "")
    actor = await _actor(db, org.id, str((payload.get("user") or {}).get("id") or ""))
    if request_id is None or actor is None:
        return _note_error(NOT_LINKED)
    problem = await _decide(db, org.id, actor, request_id, approve=False, note=note)
    return _note_error(problem) if problem else None


async def _decide(
    db: AsyncSession,
    org_id: uuid.UUID,
    actor: Actor,
    request_id: uuid.UUID,
    *,
    approve: bool,
    note: str | None,
) -> str:
    """Decide and tell everyone; returns why it was refused, or ""."""
    try:
        request = await decide(
            db,
            org_id=org_id,
            actor=actor.user.id,
            perms=actor.perms,
            request_id=request_id,
            approve=approve,
            note=note,
        )
    except LeaveError as exc:
        await db.rollback()
        # Already decided elsewhere: show the outcome on the prompts, in the
        # background so Slack gets its answer within 3 seconds.
        spawn(refresh_prompts(org_id, request_id))
        return str(exc)
    notice = stage_decision(db, org_id=org_id, request=request, decider_name=actor.user.name)
    await db.commit()
    notice.send()
    logger.info("leave_decided_from_slack", request_id=str(request_id), approve=approve)
    return ""


async def _check_may_decide(
    db: AsyncSession, org_id: uuid.UUID, actor: Actor, request_id: uuid.UUID
) -> str:
    """Why ``actor`` can't decide this request (before asking for a reason), or ""."""
    try:
        request = await load_request(db, org_id, request_id)
    except LeaveError as exc:
        return str(exc)
    approvers = await approvers_for(db, org_id, request.user_id)
    if route_for(actor.user.id, actor.perms, request.user_id, approvers) is None:
        return "Only this person's managers or HR can decide this request."
    if request.status != LeaveStatus.PENDING:
        spawn(refresh_prompts(org_id, request_id))
        return "This request was already decided or cancelled."
    return ""


def _note_error(message: str) -> dict[str, Any]:
    """Show ``message`` under the reason field and keep the modal open."""
    return {"response_action": "errors", "errors": {NOTE_BLOCK: message}}


def _uuid(value: Any) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None
