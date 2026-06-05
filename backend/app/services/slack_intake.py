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

from app.config import settings as app_settings
from app.mcp.auth import create_internal_mcp_token
from app.models.bud import BUDDocument, BUDPriority, BUDStatus
from app.models.feature_qa_session import FeatureQASession, FeatureQAStatus
from app.models.organization import Organization
from app.models.triage_session import TriageSession, TriageStatus
from app.models.user import UserRole
from app.repositories.bud import BUDRepository
from app.repositories.feature_qa_session import FeatureQASessionRepository
from app.repositories.feature_reads import FeatureReadRepository
from app.repositories.triage_session import TriageSessionRepository
from app.repositories.user import UserRepository
from app.services import slack_client
from app.services.claude_runner import (
    NO_REPO_CONTEXT,
    ClaudeRunnerConfig,
    MCPServerConfig,
    run_claude_code,
)
from app.services.embedding_service import embedding_service
from app.services.feature_lifecycle import create_planned_feature
from app.services.json_parser import parse_json_response
from app.services.prompt_builder import build_prd_prompt, build_slack_triage_prompt
from app.services.skill_loader import resolve_skill_for_org

_CANDIDATE_SIMILARITY_THRESHOLD = 0.60
_MAX_DUPLICATE_CANDIDATES = 3
# ~100 tokens of description per candidate — enough to disambiguate scope
# (narrow tweak vs broad capability) without blowing the verifier prompt.
_CANDIDATE_CONTEXT_CHARS = 400
_TERMINAL_BUD_STATUSES: tuple[BUDStatus, ...] = (BUDStatus.CLOSED, BUDStatus.DISCARDED)

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
        priority=normalize_triage_priority(session.priority),
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


async def _find_duplicate_candidates(
    db: AsyncSession,
    org: Organization,
    query_text: str,
) -> list[tuple[str, Any, float]]:
    """Gather semantically similar active BUDs and backlog Features.

    Returns up to ``_MAX_DUPLICATE_CANDIDATES`` tuples of
    ``(kind, match_object, similarity)`` above the candidate threshold.
    BUDs come first because in-flight work outranks backlog. The list
    is intentionally broad — the LLM verifier filters out false
    positives that share topic words but aren't the same feature.
    """
    query_text = query_text.strip()
    if not query_text:
        return []

    try:
        vector = await embedding_service.embed(query_text)
    except Exception:
        logger.warning("triage_dup_check_embed_failed", query=query_text[:120])
        return []

    candidates: list[tuple[str, Any, float]] = []

    bud_repo = BUDRepository(db, org_id=org.id)
    bud_match = await bud_repo.find_nearest_active_with_distance(
        vector, exclude_statuses=_TERMINAL_BUD_STATUSES
    )
    if bud_match is not None:
        bud, distance = bud_match
        similarity = 1.0 - distance
        if similarity >= _CANDIDATE_SIMILARITY_THRESHOLD:
            candidates.append(("bud", bud, similarity))

    feature_reads = FeatureReadRepository(db, org_id=org.id)
    rows = await feature_reads.semantic_search(vector, limit=2, only_active=True)
    for feature, distance in rows:
        similarity = 1.0 - distance
        if similarity >= _CANDIDATE_SIMILARITY_THRESHOLD:
            candidates.append(("feature", feature, similarity))

    return candidates[:_MAX_DUPLICATE_CANDIDATES]


def _candidate_context(text: str | None) -> str:
    """Collapse whitespace and truncate to keep the verifier prompt focused."""
    if not text:
        return ""
    collapsed = " ".join(text.split())
    if len(collapsed) <= _CANDIDATE_CONTEXT_CHARS:
        return collapsed
    return collapsed[:_CANDIDATE_CONTEXT_CHARS].rstrip() + "…"


def _format_candidate_line(idx: int, kind: str, match: Any, sim: float) -> str:
    """One numbered candidate block with title + truncated description.

    Title alone is too thin: a narrow request ("change icon") collapses
    against a broad title ("Notifications") even though the underlying
    capability is different. Including the description gives the
    verifier enough signal to distinguish scope from topic.
    """
    if kind == "bud":
        header = (
            f"{idx}. [BUD-{match.bud_number:03d}] {match.title}"
            f" — status: {match.status.value if match.status else 'unknown'},"
            f" similarity: {sim:.2f}"
        )
        body = _candidate_context(match.requirements_md)
    else:
        header = f"{idx}. [Feature] {match.feature_title} — similarity: {sim:.2f}"
        body = _candidate_context(match.description)
    return f"{header}\n   description: {body}" if body else header


async def _verify_duplicate_with_llm(
    query_text: str,
    candidates: list[tuple[str, Any, float]],
) -> tuple[str, Any, float] | None:
    """Ask the LLM to decide whether any candidate is a true duplicate.

    Semantic similarity surfaces items that share topic words, but it
    cannot distinguish "same domain" from "same feature". This focused
    one-shot call delegates that judgement to the LLM. Returns the
    confirmed candidate or ``None`` if the LLM rejects all of them.
    """
    if not candidates:
        return None

    lines = [
        _format_candidate_line(idx, kind, match, sim)
        for idx, (kind, match, sim) in enumerate(candidates, start=1)
    ]

    prompt = (
        "Decide whether a Slack feature request is a DUPLICATE of any existing"
        " item.\n\n"
        f"USER REQUEST:\n{query_text}\n\n"
        "CANDIDATES (semantically similar items already in the system):\n"
        + "\n".join(lines)
        + "\n\nTwo items are duplicates only if they describe the SAME"
        " user-facing capability or solve the SAME problem. They are NOT"
        " duplicates merely because they share generic topic words such as"
        ' "user", "data", "feature", "dashboard", "settings", "notification".'
        "\n\nIMPORTANT — scope rules:\n"
        "- A narrower change to an existing capability (e.g. tweaking an"
        " icon, copy, colour, or behaviour of one screen) is NOT a duplicate"
        " of the broader feature it touches. Reply no_match.\n"
        "- A bug report, UI polish, or follow-up enhancement is NOT a"
        " duplicate of the parent feature/BUD. Reply no_match.\n"
        "- Named-entity scope: if the user request and the candidate name"
        " DIFFERENT specific products, vendors, services, brands,"
        " organisations, geographies, regions, markets, or integration"
        " targets, they are NOT duplicates even when the surrounding"
        " capability sounds identical. A request for variant A of a"
        " capability is not satisfied by an in-flight item for variant B."
        " Reply no_match and let triage create a new BUD.\n"
        '- Only reply "match" when the user request and the candidate would'
        " produce essentially the same deliverable.\n"
        "When in doubt, prefer no_match — a false duplicate silently drops"
        " the request, while a missed duplicate just creates one extra BUD"
        " that PMs can merge later.\n\n"
        "Respond with exactly one JSON object, no markdown, no extra text:\n"
        '{"verdict": "match" or "no_match", "matched_index":'
        " <1-based index or null>}"
    )

    result = await run_claude_code(
        prompt=prompt,
        working_dir=NO_REPO_CONTEXT,
        config=ClaudeRunnerConfig(max_turns=1, timeout_seconds=45, mcp=None),
    )

    if not result.success:
        logger.warning("triage_dup_verify_failed", error=result.error)
        return None

    response = parse_json_response(result.output)
    if response is None or response.get("verdict") != "match":
        return None

    matched_index = response.get("matched_index")
    if not isinstance(matched_index, int) or not 1 <= matched_index <= len(candidates):
        return None

    return candidates[matched_index - 1]


async def _post_duplicate_message(
    bot_token: str,
    session: TriageSession,
    kind: str,
    match: Any,
    similarity: float,
) -> None:
    """Format and post a duplicate-found reply, including delivery date."""
    if kind == "bud":
        bud_ref = f"BUD-{match.bud_number:03d}"
        status_str = match.status.value if match.status else "unknown"
        parts = [
            f"⚠️ *{bud_ref}* — {match.title} is already *{status_str}* and being tracked."
            f" Similarity {similarity:.0%} — no new BUD needed."
        ]
        if match.prod_p70_date:
            parts.append(f"📅 Estimated delivery: *{match.prod_p70_date.strftime('%Y-%m-%d')}*")
        elif match.current_phase_deadline:
            parts.append(
                f"📅 Current phase deadline: *{match.current_phase_deadline.strftime('%Y-%m-%d')}*"
            )
        message = "\n".join(parts)
    else:
        message = (
            f"ℹ️ *{match.feature_title}* is already tracked in the product backlog"
            f" (similarity {similarity:.0%})."
        )

    await slack_client.chat_post_message(
        bot_token, session.slack_channel, message, thread_ts=session.thread_ts
    )


async def _seed_qa_session_for_match(
    db: AsyncSession,
    org: Organization,
    session: TriageSession,
    kind: str,
    match: Any,
    query_text: str,
) -> None:
    """Open a FeatureQASession on the same thread as a triage duplicate match.

    The triage flow is about to mark itself ``REJECTED`` (the user's
    request is "already tracked"). Without a Q&A session, any reply in
    the thread — e.g. *"Including patient name?"* or *"AI is mixing up
    the entities"* — is silently dropped, because ``continue_triage``
    only fires for ``INTERVIEWING / CHECKING`` sessions and
    ``continue_feature_qa`` finds no session for the thread.

    Opening a Q&A session here keeps the conversation alive: the
    matched candidate goes into ``context.candidates`` in the same
    shape the ``clarify`` action emits, so the Q&A skill's existing
    "Drill-down on the prior result" branch can pick it up on the
    next reply without any new vocabulary in the skill prompt.

    Idempotent: if a Q&A session already exists for this thread (which
    can only happen if the user @-mentioned the bot first and then
    reacted 🧠), we leave it alone. The QA session's unique constraint
    on ``(org_id, channel, thread_ts)`` would reject a duplicate insert
    anyway; this just avoids the round-trip.
    """
    qa_repo = FeatureQASessionRepository(db, org_id=org.id)
    existing = await qa_repo.get_by_thread(session.slack_channel, session.thread_ts)
    if existing is not None:
        return

    if kind == "bud":
        candidate = {
            "kind": "bud",
            "id": str(match.id),
            "bud_number": match.bud_number,
            "title": match.title,
        }
    else:
        candidate = {
            "kind": "feature",
            "id": str(match.id),
            "title": match.feature_title,
        }

    qa_session = FeatureQASession(
        org_id=org.id,
        channel=session.slack_channel,
        thread_ts=session.thread_ts,
        requester_slack_user_id=session.requester_slack_id,
        original_question=query_text,
        status=FeatureQAStatus.AWAITING_USER,
        context={"candidates": [candidate]},
    )
    await qa_repo.create(qa_session)
    logger.info(
        "triage_seeded_qa_session_on_duplicate",
        triage_session_id=str(session.id),
        qa_session_id=str(qa_session.id),
        kind=kind,
    )


def _build_duplicate_query(
    session: TriageSession,
    thread_messages: list[dict[str, Any]] | None,
) -> str:
    """Combine the original message with user replies for richer matching."""
    parts = [session.original_text or ""]
    if thread_messages:
        for msg in thread_messages:
            if msg.get("bot_id"):
                continue
            text = msg.get("text", "")
            if text:
                parts.append(text)
    return " ".join(parts).strip()


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

    is_first_turn = len(thread_messages) <= 2
    progress_msg = (
        "_⏳ Checking for existing features and BUDs..._"
        if is_first_turn
        else "_🤔 Reviewing your response..._"
    )
    await slack_client.chat_post_message(
        bot_token, session.slack_channel, progress_msg, thread_ts=session.thread_ts
    )

    # Duplicate detection: semantic search finds candidates (broad net at
    # 0.60+ similarity), then an LLM call verifies whether any candidate
    # is actually the same feature. The two-stage check stops false
    # positives that share generic topic words (e.g. "user", "dashboard").
    query_text = _build_duplicate_query(session, thread_messages)
    candidates = await _find_duplicate_candidates(db, org, query_text)
    duplicate = await _verify_duplicate_with_llm(query_text, candidates) if candidates else None
    if duplicate is not None:
        kind, match, similarity = duplicate
        await _post_duplicate_message(bot_token, session, kind, match, similarity)
        # Hand the thread over to the Q&A flow so any follow-up reply
        # ("Including patient name?", "AI is mixing up the entities…")
        # is answered instead of dropped. Without this, the triage
        # session goes REJECTED below and no other handler claims the
        # thread — see _seed_qa_session_for_match for the seam details.
        await _seed_qa_session_for_match(db, org, session, kind, match, query_text)
        session.status = TriageStatus.REJECTED
        logger.info(
            "triage_duplicate_detected",
            session_id=str(session.id),
            kind=kind,
            similarity=round(similarity, 4),
            candidate_count=len(candidates),
        )
        return

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

    skill = await resolve_skill_for_org("slackTriage", org.id, db, fallback_slug=skill_name)

    token = create_internal_mcp_token(org.id)
    mcp: MCPServerConfig | None = MCPServerConfig(
        backend_url=app_settings.mcp_backend_url,
        mcp_token=token,
        tool_names=["check_feature_exists", "get_bud_context", "search_bugs"],
    )

    result = await run_claude_code(
        prompt=prompt,
        working_dir=NO_REPO_CONTEXT,
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

    response = parse_json_response(result.output)
    if response is None:
        logger.warning(
            "triage_agent_parse_failed",
            session_id=str(session.id),
            output_length=len(result.output),
            output_head=result.output[:500],
            output_tail=result.output[-500:] if len(result.output) > 500 else "",
        )
        await slack_client.chat_post_message(
            bot_token,
            session.slack_channel,
            "⚠️ Couldn't read the triage response. Please react 🧠 again to retry.",
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

    elif action == "exists":
        # Duplicate feature or active BUD found — close the session without creating a BUD
        kind = data.get("kind", "feature")
        title = data.get("title", "Unknown feature")

        if kind == "bud":
            bud_number = data.get("bud_number")
            status_str = data.get("status", "")
            bud_ref = f"BUD-{int(bud_number):03d}" if bud_number is not None else "BUD-???"
            parts = [
                f"⚠️ *{bud_ref}* — {title} is already *{status_str}* and being tracked."
                " No new BUD needed."
            ]
            if bud_number is not None:
                bud_repo = BUDRepository(db, org_id=org.id)
                existing_bud = await bud_repo.get_by_number(int(bud_number))
                if existing_bud:
                    if existing_bud.prod_p70_date:
                        date_str = existing_bud.prod_p70_date.strftime("%Y-%m-%d")
                        parts.append(f"📅 Estimated delivery: *{date_str}*")
                    elif existing_bud.current_phase_deadline:
                        date_str = existing_bud.current_phase_deadline.strftime("%Y-%m-%d")
                        parts.append(f"📅 Current phase deadline: *{date_str}*")
            message = "\n".join(parts)
        else:
            message = f"ℹ️ *{title}* is already tracked in the product backlog."

        await slack_client.chat_post_message(
            bot_token,
            session.slack_channel,
            message,
            thread_ts=session.thread_ts,
        )
        session.status = TriageStatus.REJECTED
        logger.info(
            "triage_duplicate_detected",
            session_id=str(session.id),
            kind=kind,
            title=title,
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
    bud_ref = f"BUD-{bud.bud_number:03d}"
    skill = await resolve_skill_for_org("bud", org.id, db, fallback_slug="product-manager")

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
            working_dir=NO_REPO_CONTEXT,
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


# Free-text priority synonyms accepted from the triage form / Slack
# replies. Keys are lowercase and contain only [a-z0-9] — the lookup
# strips every other character first, so ``"P-0"``, ``"P0!"`` and
# ``"sev 0"`` all collapse to ``"p0"``. Anything not in this map (or
# NULL / empty) falls through to the default P2, matching the column's
# NOT NULL DEFAULT 'P2'.
_PRIORITY_ALIASES: dict[str, BUDPriority] = {
    "p0": BUDPriority.P0,
    "sev0": BUDPriority.P0,
    "critical": BUDPriority.P0,
    "urgent": BUDPriority.P0,
    "blocker": BUDPriority.P0,
    "asap": BUDPriority.P0,
    "highest": BUDPriority.P0,
    "p1": BUDPriority.P1,
    "sev1": BUDPriority.P1,
    "high": BUDPriority.P1,
    "p2": BUDPriority.P2,
    "sev2": BUDPriority.P2,
    "medium": BUDPriority.P2,
    "normal": BUDPriority.P2,
    "p3": BUDPriority.P3,
    "sev3": BUDPriority.P3,
    "low": BUDPriority.P3,
    "minor": BUDPriority.P3,
    "lowest": BUDPriority.P3,
    "nicetohave": BUDPriority.P3,
}


def normalize_triage_priority(raw: str | None) -> BUDPriority:
    """Map a free-text priority value from triage into ``BUDPriority``.

    The triage form has historically accepted any string. The structured
    BUD column needs one of P0..P3, so unknown / missing values default
    to P2 (matching the column's server_default).

    Unknown-but-truthy values are logged so operators can spot bad
    triage input — empty / NULL stays silent because that's the
    documented "no opinion" case.
    """
    if not raw:
        return BUDPriority.P2
    key = "".join(ch for ch in raw.lower() if ch.isalnum())
    if key in _PRIORITY_ALIASES:
        return _PRIORITY_ALIASES[key]
    logger.warning("triage_priority_unknown", raw=raw)
    return BUDPriority.P2


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
