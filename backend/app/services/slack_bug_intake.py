# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Slack-based bug intake triage service.

Orchestrates the 🐛 emoji → bug triage → approval → Bug creation flow.
Extracted from slack_intake.py to keep file sizes manageable. Shares the
same TriageSession model, session routing, and Slack client.
"""

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization import Organization
from app.models.triage_session import TriageSession, TriageStatus
from app.models.user import User, UserRole
from app.repositories.triage_session import TriageSessionRepository
from app.services import slack_client

logger = structlog.get_logger(__name__)

# Roles allowed to approve bug reports (same as BUD triage)
_PM_ROLES = {UserRole.PM, UserRole.ORG_OWNER, UserRole.ADMIN}


async def start_bug_triage(
    db: AsyncSession,
    org: Organization,
    bot_token: str,
    channel: str,
    message_ts: str,
    requester_slack_id: str,
) -> None:
    """Start a bug triage session when a 🐛 emoji is added to a message.

    Same flow as ``start_triage`` but creates a session with
    ``session_type="bug"`` and uses a bug-specific prompt that asks
    for: title, description, steps to reproduce, severity, and module.
    """
    repo = TriageSessionRepository(db, org_id=org.id)

    existing = await repo.get_by_original_msg(channel, message_ts)
    if existing:
        logger.info("bug_triage_already_exists", channel=channel, message_ts=message_ts)
        return

    messages = await slack_client.conversations_history(
        bot_token, channel, latest=message_ts, inclusive=True, limit=1
    )
    if not messages:
        logger.warning("bug_triage_message_not_found", channel=channel, message_ts=message_ts)
        return

    original_text = messages[0].get("text", "")
    requester_name = (
        messages[0].get("user_profile", {}).get("real_name") or requester_slack_id
    )

    thread_result = await slack_client.chat_post_message(
        bot_token,
        channel,
        (
            "🐛 *Bug reported!* Let me gather some details.\n"
            "I'll ask follow-up questions if I need more info."
        ),
        thread_ts=message_ts,
    )
    thread_ts = thread_result.get("ts", message_ts) if thread_result else message_ts

    session = TriageSession(
        org_id=org.id,
        slack_channel=channel,
        thread_ts=thread_ts,
        original_msg_ts=message_ts,
        requester_slack_id=requester_slack_id,
        requester_name=requester_name,
        original_text=original_text,
        status=TriageStatus.INTERVIEWING,
        session_type="bug",
    )
    await repo.create(session)
    await db.flush()

    logger.info("bug_triage_session_created", session_id=str(session.id), channel=channel)
    await run_bug_triage_agent(db, org, bot_token, session)


async def handle_bug_approval(
    db: AsyncSession,
    org: Organization,
    bot_token: str,
    channel: str,
    message_ts: str,
    approver_slack_id: str,
    approved: bool,
) -> None:
    """Handle approval/rejection of a bug triage summary.

    On approval: creates a Bug record with extracted fields, generates
    embedding, and auto-links to the closest BUD.
    """
    repo = TriageSessionRepository(db, org_id=org.id)
    session = await repo.get_by_summary_msg(channel, message_ts)
    if not session or session.session_type != "bug":
        return
    if session.status != TriageStatus.AWAITING_PM:
        return

    if not approved:
        session.status = TriageStatus.REJECTED
        await slack_client.chat_post_message(
            bot_token, channel,
            "❌ Bug report discarded.",
            thread_ts=session.thread_ts,
        )
        return

    # Resolve approver + verify PM/admin role
    from sqlalchemy import select as sql_select

    from app.models.user import OrgToUser

    stmt = (
        sql_select(User, OrgToUser.role)
        .join(OrgToUser, OrgToUser.user_id == User.id)
        .where(OrgToUser.org_id == org.id, User.slack_id == approver_slack_id)
        .limit(1)
    )
    result = await db.execute(stmt)
    row = result.first()
    if not row:
        await slack_client.chat_post_message(
            bot_token, channel,
            "⚠️ Could not resolve your user account.",
            thread_ts=session.thread_ts,
        )
        return

    approver, approver_role = row
    approver_role_val = UserRole(approver_role) if approver_role else None
    if approver_role_val not in _PM_ROLES:
        await slack_client.chat_post_message(
            bot_token, channel,
            "⚠️ Only PMs and admins can approve bug reports.",
            thread_ts=session.thread_ts,
        )
        return

    # Build bug from triage context
    ctx = session.triage_context or {}
    from app.models.bug import Bug

    bug = Bug(
        org_id=org.id,
        title=ctx.get("title", session.feature_name or "Untitled bug"),
        description=ctx.get("description", session.original_text),
        severity=ctx.get("severity", "medium"),
        module=ctx.get("module"),
        reporter_id=approver.id,
    )
    db.add(bug)
    await db.flush()
    await db.refresh(bug)

    # Embed + auto-link to closest BUD
    try:
        from app.services.bug_linker import embed_and_link_bug

        matched_bud = await embed_and_link_bug(db, org.id, bug)
    except Exception:
        matched_bud = None
        logger.warning("bug_triage_embed_failed", bug_id=str(bug.id), exc_info=True)

    session.status = TriageStatus.BUD_CREATED

    link_msg = ""
    if matched_bud:
        link_msg = f" Linked to *BUD-{matched_bud.bud_number:03d}*."

    await slack_client.chat_post_message(
        bot_token, channel,
        f"✅ Bug created: *{bug.title}* (severity: {bug.severity}).{link_msg}",
        thread_ts=session.thread_ts,
    )

    logger.info(
        "bug_triage_bug_created",
        session_id=str(session.id),
        bug_id=str(bug.id),
        linked_bud=matched_bud.bud_number if matched_bud else None,
    )


async def run_bug_triage_agent(
    db: AsyncSession,
    org: Organization,
    bot_token: str,
    session: TriageSession,
) -> None:
    """Run the bug triage agent — extracts bug details via conversation."""
    thread_messages = await slack_client.conversations_replies(
        bot_token, session.slack_channel, session.thread_ts
    )

    prompt = _build_bug_triage_prompt(
        session_status=session.status,
        original_text=session.original_text or "",
        thread_messages=thread_messages,
        triage_context=session.triage_context,
    )

    from app.services.claude_runner import ClaudeRunnerConfig, run_claude_code
    from app.services.slack_intake import _parse_agent_response

    result = await run_claude_code(
        prompt=prompt,
        config=ClaudeRunnerConfig(max_turns=5, timeout_seconds=60),
    )

    if not result.success:
        await slack_client.chat_post_message(
            bot_token, session.slack_channel,
            "⚠️ Bug triage is taking longer than expected. A team member will follow up.",
            thread_ts=session.thread_ts,
        )
        return

    response = _parse_agent_response(result.output)
    if response is None:
        await slack_client.chat_post_message(
            bot_token, session.slack_channel,
            result.output[:3000],
            thread_ts=session.thread_ts,
        )
        return

    action = response.get("action", "")
    data = response.get("data", {})

    if action == "question":
        await slack_client.chat_post_message(
            bot_token, session.slack_channel,
            data.get("message", "Could you provide more details about the bug?"),
            thread_ts=session.thread_ts,
        )
    elif action == "summary":
        session.feature_name = data.get("title", "")
        session.triage_context = data.get("context", {})
        session.status = TriageStatus.AWAITING_PM

        summary_text = data.get("message", "Bug summary unavailable.")
        summary_result = await slack_client.chat_post_message(
            bot_token, session.slack_channel,
            summary_text,
            thread_ts=session.thread_ts,
        )
        if summary_result:
            session.summary_msg_ts = summary_result.get("ts")

        logger.info(
            "bug_triage_summary_posted",
            session_id=str(session.id),
            title=session.feature_name,
        )


def _build_bug_triage_prompt(
    session_status: str,
    original_text: str,
    thread_messages: list[dict],
    triage_context: dict | None,
) -> str:
    """Build the system prompt for the bug triage agent."""
    thread_text = "\n".join(
        f"{'[Bot]' if m.get('bot_id') else '[User]'}: {m.get('text', '')}"
        for m in thread_messages
    )

    return f"""You are a bug triage assistant. Your job is to gather enough information
to create a complete bug report.

REQUIRED information (ask if missing):
- Title: a concise summary of the bug
- Description: what happened and what was expected
- Steps to reproduce: how to trigger the bug
- Severity: low, medium, high, or critical

OPTIONAL but helpful:
- Module / area of the application affected
- Expected vs actual behavior

CONVERSATION SO FAR:
{thread_text}

EXISTING CONTEXT:
{triage_context or 'None yet'}

INSTRUCTIONS:
- If you have ALL required info, respond with a JSON summary action.
- If ANY required info is missing, respond with a question action asking for it.
- Be conversational and friendly.

RESPOND WITH EXACTLY ONE JSON OBJECT:

For a follow-up question:
{{"action": "question", "data": {{"message": "your question here"}}}}

For a complete summary (when you have all info):
{{"action": "summary", "data": {{
  "title": "concise bug title",
  "message": "🐛 **Bug Summary**\\n**Title:** ...\\n**Severity:** ...\\nReact ✅ / ❌",
  "context": {{
    "title": "...",
    "description": "full description with steps to reproduce",
    "severity": "low|medium|high|critical",
    "module": "optional module name"
  }}
}}}}
"""
