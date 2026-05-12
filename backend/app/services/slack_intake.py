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

"""Slack-based feature intake triage service.

Orchestrates the brain-emoji → triage → PM approval → BUD creation flow.
Each function is called from background tasks in the Slack webhook handler.
"""

from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bud import BUDDocument, BUDStatus
from app.models.organization import Organization
from app.models.triage_session import TriageSession, TriageStatus
from app.models.user import UserRole
from app.repositories.bud import BUDRepository
from app.repositories.triage_session import TriageSessionRepository
from app.repositories.user import UserRepository
from app.services import slack_client
from app.services.feature_lifecycle import create_planned_feature
from app.services.prompt_builder import build_prd_prompt, build_slack_triage_prompt

logger = structlog.get_logger(__name__)

# Roles allowed to approve/reject triage summaries
_PM_ROLES = {UserRole.PM, UserRole.ORG_OWNER, UserRole.ADMIN}


async def start_triage(
    db: AsyncSession,
    org: Organization,
    bot_token: str,
    channel: str,
    message_ts: str,
    requester_slack_id: str,
) -> None:
    """Start a new triage session when a brain emoji is added to a message.

    Fetches the original message, creates a TriageSession, posts an
    acknowledgment in-thread, and runs the triage agent.

    Args:
        db: Async database session.
        org: The resolved organization.
        bot_token: Decrypted Slack bot token.
        channel: Slack channel ID.
        message_ts: Timestamp of the message that received the brain emoji.
        requester_slack_id: Slack user ID of whoever added the emoji.
    """
    repo = TriageSessionRepository(db, org_id=org.id)

    # Check if a session already exists for this message
    existing = await repo.get_by_original_msg(channel, message_ts)
    if existing:
        logger.info("triage_already_exists", channel=channel, message_ts=message_ts)
        return

    # Fetch the original message text
    messages = await slack_client.conversations_history(
        bot_token, channel, latest=message_ts, inclusive=True, limit=1
    )
    if not messages:
        logger.warning("triage_original_message_not_found", channel=channel, ts=message_ts)
        return

    original_text = messages[0].get("text", "")

    # Resolve the requester's display name from Slack
    requester_name = requester_slack_id
    user_info = await slack_client.users_info(bot_token, requester_slack_id)
    if user_info:
        requester_name = (
            user_info.get("real_name")
            or user_info.get("profile", {}).get("display_name")
            or requester_slack_id
        )

    # Acknowledge with eyes emoji on the original message
    await slack_client.reactions_add(bot_token, channel, message_ts, "eyes")

    # Post initial thread reply
    initial_reply = await slack_client.chat_post_message(
        bot_token,
        channel,
        "🔍 Analyzing this feature request...",
        thread_ts=message_ts,
    )
    if not initial_reply:
        logger.warning("triage_initial_reply_failed", channel=channel)
        return

    # Create the triage session (thread_ts = original message ts for top-level messages)
    session = TriageSession(
        org_id=org.id,
        slack_channel=channel,
        thread_ts=message_ts,
        original_msg_ts=message_ts,
        requester_slack_id=requester_slack_id,
        requester_name=requester_name,
        original_text=original_text,
        status=TriageStatus.INTERVIEWING,
    )
    await repo.create(session)
    await db.flush()

    logger.info(
        "triage_session_created",
        session_id=str(session.id),
        channel=channel,
        thread_ts=message_ts,
    )

    # Run the triage agent for the first turn
    await _run_triage_agent(db, org, bot_token, session)


async def continue_triage(
    db: AsyncSession,
    org: Organization,
    bot_token: str,
    channel: str,
    thread_ts: str,
    new_message: str,
    sender_slack_id: str,
) -> None:
    """Continue an active triage session when a user replies in the thread.

    Args:
        db: Async database session.
        org: The resolved organization.
        bot_token: Decrypted Slack bot token.
        channel: Slack channel ID.
        thread_ts: Thread parent timestamp.
        new_message: The new reply text.
        sender_slack_id: Slack user ID of the sender.
    """
    repo = TriageSessionRepository(db, org_id=org.id)
    session = await repo.get_by_thread(channel, thread_ts)

    if session is None:
        return  # Not a triage thread

    # Only continue if session is in an active state
    if session.status not in (TriageStatus.INTERVIEWING, TriageStatus.CHECKING):
        return

    logger.info(
        "triage_continue",
        session_id=str(session.id),
        sender=sender_slack_id,
        session_type=session.session_type,
    )

    if session.session_type == "bug":
        from app.services.slack_bug_intake import run_bug_triage_agent

        await run_bug_triage_agent(db, org, bot_token, session)
    else:
        await _run_triage_agent(db, org, bot_token, session)


async def handle_pm_approval(
    db: AsyncSession,
    org: Organization,
    bot_token: str,
    channel: str,
    message_ts: str,
    approver_slack_id: str,
    approved: bool,
) -> None:
    """Handle a PM's approval or rejection reaction on a triage summary.

    Args:
        db: Async database session.
        org: The resolved organization.
        bot_token: Decrypted Slack bot token.
        channel: Slack channel ID.
        message_ts: Timestamp of the summary message that was reacted to.
        approver_slack_id: Slack user ID of the approver.
        approved: True if approved (✅), False if rejected (❌).
    """
    repo = TriageSessionRepository(db, org_id=org.id)
    session = await repo.get_by_summary_msg(channel, message_ts)

    if session is None:
        return  # Not a triage summary message

    # Route bug sessions to the bug-specific approval handler
    if session.session_type == "bug":
        from app.services.slack_bug_intake import handle_bug_approval

        await handle_bug_approval(
            db,
            org,
            bot_token,
            channel,
            message_ts,
            approver_slack_id,
            approved,
        )
        return

    if session.status != TriageStatus.AWAITING_PM:
        return  # Session not in approval state

    # Verify the approver is a PM or org owner
    pair = await UserRepository(db).get_by_slack_id_with_role(org.id, approver_slack_id)
    approver = pair[0] if pair else None
    approver_role_val = pair[1] if pair else None

    if approver is None or approver_role_val not in _PM_ROLES:
        await slack_client.chat_post_message(
            bot_token,
            channel,
            "⚠️ Only PMs and org owners can approve feature requests.",
            thread_ts=session.thread_ts,
        )
        return

    if not approved:
        session.status = TriageStatus.REJECTED
        await slack_client.chat_post_message(
            bot_token,
            channel,
            f"❌ Feature request declined by <@{approver_slack_id}>.",
            thread_ts=session.thread_ts,
        )
        logger.info("triage_rejected", session_id=str(session.id))
        return

    # Approved — create BUD
    session.status = TriageStatus.APPROVED

    bud_repo = BUDRepository(db, org_id=org.id)
    next_number = await bud_repo.next_bud_number()

    requirements_md = _build_bud_content(session)

    bud = BUDDocument(
        org_id=org.id,
        bud_number=next_number,
        title=session.feature_name or "Untitled Feature Request",
        status=BUDStatus.BUD,
        requirements_md=requirements_md,
        metadata_={"source": "slack_triage", "triage_session_id": str(session.id)},
    )
    await bud_repo.create(bud)

    session.bud_id = bud.id
    session.status = TriageStatus.BUD_CREATED

    # Create feature registry entry
    await create_planned_feature(db, org.id, next_number, bud.title, requirements_md)

    # Record timeline events
    from app.services.bud_assignment import auto_assign_for_phase
    from app.services.bud_timeline import record_event

    await record_event(
        db,
        org.id,
        bud.id,
        "created",
        detail={"source": "slack_triage", "triage_session_id": str(session.id)},
    )
    await record_event(
        db,
        org.id,
        bud.id,
        "requested",
        actor_name=session.requester_name,
        detail={
            "requester_name": session.requester_name,
            "slack_id": session.requester_slack_id,
            "channel": session.slack_channel,
        },
    )
    await record_event(
        db,
        org.id,
        bud.id,
        "approved",
        actor_id=approver.id,
        actor_name=approver.name,
        detail={
            "approver_name": approver.name,
            "approver_slack_id": approver_slack_id,
        },
    )
    await auto_assign_for_phase(db, org.id, bud, BUDStatus.BUD)

    bud_ref = f"BUD-{next_number:03d}"
    await slack_client.chat_post_message(
        bot_token,
        channel,
        f"✅ *{bud_ref}* created: *{bud.title}*\nApproved by <@{approver_slack_id}>.",
        thread_ts=session.thread_ts,
    )

    logger.info(
        "triage_bud_created",
        session_id=str(session.id),
        bud_id=str(bud.id),
        bud_number=next_number,
    )

    # Auto-trigger PRD agent via the agent task system
    from app.services.bud_agent_trigger import create_agent_task_for_stage

    await create_agent_task_for_stage(
        bud,
        "bud",
        org.id,
        db,
        triggered_by=approver.id,
        force=True,
    )


# ── Private helpers ────────────────────────────────────────────────


async def _run_triage_agent(
    db: AsyncSession,
    org: Organization,
    bot_token: str,
    session: TriageSession,
) -> None:
    """Run the triage agent and process its response.

    Fetches thread history, builds a prompt, runs the agent, and posts
    the response back to the Slack thread.
    """
    # Fetch full thread history
    thread_messages = await slack_client.conversations_replies(
        bot_token, session.slack_channel, session.thread_ts
    )

    skill_name = "slack-triage"
    prompt = await build_slack_triage_prompt(
        skill_name=skill_name,
        session_status=session.status,
        original_text=session.original_text or "",
        thread_messages=thread_messages,
        triage_context=session.triage_context,
        org_id=org.id,
        db=db,
    )

    from app.services.claude_runner import ClaudeRunnerConfig, MCPServerConfig, run_claude_code
    from app.services.skill_loader import load_skill

    skill = load_skill(skill_name)

    # Only set up MCP auth when the agent has enough context to check for
    # existing features. On the first turn (INTERVIEWING, no thread replies)
    # the agent just asks questions — no MCP tools needed.
    needs_mcp = len(thread_messages) > 2 or session.status != TriageStatus.INTERVIEWING

    mcp: MCPServerConfig | None = None
    if needs_mcp:
        from app.config import settings as app_settings
        from app.mcp.auth import create_internal_mcp_token

        token = create_internal_mcp_token(org.id)
        mcp = MCPServerConfig(
            backend_url=app_settings.mcp_backend_url,
            mcp_token=token,
            tool_names=["check_feature_exists", "search_bugs"],
        )

    result = await run_claude_code(
        prompt=prompt,
        config=ClaudeRunnerConfig(max_turns=skill.max_turns, timeout_seconds=120, mcp=mcp),
    )

    if not result.success:
        await slack_client.chat_post_message(
            bot_token,
            session.slack_channel,
            "⚠️ Triage is taking longer than expected. A team member will follow up.",
            thread_ts=session.thread_ts,
        )
        logger.warning(
            "triage_agent_failed",
            session_id=str(session.id),
            error=result.error,
        )
        return

    # Parse agent response
    response = _parse_agent_response(result.output)
    if response is None:
        # Agent output wasn't valid JSON — post raw output as fallback
        await slack_client.chat_post_message(
            bot_token,
            session.slack_channel,
            result.output[:3000],
            thread_ts=session.thread_ts,
        )
        return

    action = response.get("action", "")
    data = response.get("data", {})

    if action == "question":
        # Post follow-up question
        await slack_client.chat_post_message(
            bot_token,
            session.slack_channel,
            data.get("message", "Could you provide more details?"),
            thread_ts=session.thread_ts,
        )

    elif action == "summary":
        # Post triage summary and transition to awaiting_pm
        session.feature_name = data.get("feature_name", "")
        session.priority = data.get("priority", "")
        session.triage_context = data.get("context", {})
        session.status = TriageStatus.AWAITING_PM

        summary_result = await slack_client.chat_post_message(
            bot_token,
            session.slack_channel,
            data.get("message", "Triage summary unavailable."),
            thread_ts=session.thread_ts,
        )

        if summary_result:
            session.summary_msg_ts = summary_result.get("ts")

        logger.info(
            "triage_summary_posted",
            session_id=str(session.id),
            feature_name=session.feature_name,
            priority=session.priority,
        )


def _parse_agent_response(output: str) -> dict[str, Any] | None:
    """Parse the agent's JSON response, handling common formatting issues."""
    from app.services.json_parser import parse_json_response

    return parse_json_response(output)


async def _run_prd_agent(
    db: AsyncSession,
    org: Organization,
    bot_token: str,
    bud: BUDDocument,
    session: TriageSession,
) -> None:
    """Run the Product Manager agent to enrich a BUD with a full initial PRD.

    Called as a background task after triage approval creates a BUD.
    Follows the same MCP auth pattern as _run_triage_agent and scan_pipeline.

    Args:
        db: Async database session.
        org: The resolved organization.
        bot_token: Decrypted Slack bot token.
        bud: The newly created BUD document.
        session: The triage session that produced this BUD.
    """
    from app.config import settings as app_settings
    from app.mcp.auth import create_internal_mcp_token
    from app.services.claude_runner import (
        ClaudeRunnerConfig,
        MCPServerConfig,
        run_claude_code,
    )
    from app.services.skill_loader import load_skill

    bud_ref = f"BUD-{bud.bud_number:03d}"
    skill = load_skill("product-manager")

    try:
        prompt = await build_prd_prompt(
            skill_name="product-manager",
            bud_number=bud.bud_number,
            bud_title=bud.title,
            triage_context=session.triage_context or {},
            requirements_md=bud.requirements_md or "",
            org_id=org.id,
            db=db,
        )

        token = create_internal_mcp_token(org.id)
        mcp = MCPServerConfig(
            backend_url=app_settings.mcp_backend_url,
            mcp_token=token,
        )
        result = await run_claude_code(
            prompt=prompt,
            config=ClaudeRunnerConfig(max_turns=skill.max_turns, timeout_seconds=300, mcp=mcp),
        )

        if result.success:
            await slack_client.chat_post_message(
                bot_token,
                session.slack_channel,
                f"📝 Initial PRD drafted for *{bud_ref}*",
                thread_ts=session.thread_ts,
            )
            logger.info("prd_agent_completed", bud_ref=bud_ref, session_id=str(session.id))
        else:
            logger.warning(
                "prd_agent_failed",
                bud_ref=bud_ref,
                error=result.error,
            )
    except Exception:
        logger.exception("prd_agent_error", bud_ref=bud_ref)


def _build_bud_content(session: TriageSession) -> str:
    """Build BUD markdown content from triage session data."""
    ctx = session.triage_context or {}
    lines = [
        f"# {session.feature_name or 'Feature Request'}",
        "",
        "## Origin",
        f"- **Source:** Slack triage (channel: {session.slack_channel})",
        f"- **Requested by:** {session.requester_name or session.requester_slack_id}",
        f"- **Priority:** {session.priority or 'TBD'}",
        "",
    ]

    if ctx.get("merchant_name"):
        lines.append(f"**Merchant:** {ctx['merchant_name']}")
    if ctx.get("business_justification"):
        lines.extend(["", "## Business Context", ctx["business_justification"]])
    if ctx.get("user_impact"):
        lines.extend(["", "## User Impact", ctx["user_impact"]])
    if ctx.get("urgency"):
        lines.extend(["", "## Urgency", ctx["urgency"]])
    if ctx.get("compliance"):
        lines.extend(["", "## Compliance", "This feature has regulatory/legal drivers."])

    lines.extend(["", "---", f"_Auto-created from triage session {session.id}_"])

    return "\n".join(lines)
