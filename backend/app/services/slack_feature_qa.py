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

"""Slack feature Q&A service.

Handles @mention and ❓-reaction events: runs the slack-feature-qa agent,
interprets its JSON response, and posts formatted replies back to the thread.
"""

import re
import uuid
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings as app_settings
from app.mcp.auth import create_internal_mcp_token
from app.models.feature_qa_session import FeatureQASession, FeatureQAStatus
from app.models.organization import Organization
from app.repositories.bud import BUDRepository
from app.repositories.feature import FeatureRepository
from app.repositories.feature_qa_session import FeatureQASessionRepository
from app.repositories.user import UserRepository
from app.services import slack_client
from app.services.claude_runner import (
    NO_REPO_CONTEXT,
    ClaudeRunnerConfig,
    MCPServerConfig,
    run_claude_code,
)
from app.services.json_parser import parse_json_response
from app.services.skill_loader import load_skill
from app.services.slack_feature_qa_reply import (
    format_bud_answer,
    format_clarify_reply,
    format_feature_answer,
)

logger = structlog.get_logger(__name__)

_BOT_MENTION_RE = re.compile(r"<@[A-Z0-9]+>")
_SKILL_NAME = "slack-feature-qa"


async def start_feature_qa(
    db: AsyncSession,
    org: Organization,
    bot_token: str,
    channel: str,
    thread_ts: str,
    requester_slack_user_id: str,
    question_text: str,
) -> None:
    """Start a new feature Q&A session for a Slack @mention or ❓ reaction.

    Args:
        db: Async database session.
        org: The resolved organization.
        bot_token: Decrypted Slack bot token.
        channel: Slack channel ID.
        thread_ts: Thread anchor timestamp (message ts for reactions, event ts for mentions).
        requester_slack_user_id: Slack user ID of the person asking.
        question_text: The extracted question text (bot mention stripped).
    """
    repo = FeatureQASessionRepository(db, org_id=org.id)

    existing = await repo.get_by_thread(channel, thread_ts)
    if existing:
        logger.info("feature_qa_session_already_exists", channel=channel, thread_ts=thread_ts)
        return

    ack = await slack_client.chat_post_message(
        bot_token,
        channel,
        "🔍 Looking that up...",
        thread_ts=thread_ts,
    )
    if not ack:
        logger.warning("feature_qa_ack_failed", channel=channel)
        return

    session = FeatureQASession(
        org_id=org.id,
        channel=channel,
        thread_ts=thread_ts,
        requester_slack_user_id=requester_slack_user_id,
        original_question=question_text,
        status=FeatureQAStatus.AWAITING_USER,
    )
    await repo.create(session)
    await db.flush()

    logger.info(
        "feature_qa_session_created",
        session_id=str(session.id),
        channel=channel,
        thread_ts=thread_ts,
    )

    await _run_qa_agent(db, org, bot_token, session, thread_messages=None)


async def continue_feature_qa(
    db: AsyncSession,
    org: Organization,
    bot_token: str,
    channel: str,
    thread_ts: str,
    user_reply: str,
) -> None:
    """Continue an active feature Q&A session on a user's thread reply.

    Args:
        db: Async database session.
        org: The resolved organization.
        bot_token: Decrypted Slack bot token.
        channel: Slack channel ID.
        thread_ts: Thread anchor timestamp.
        user_reply: The new reply text.
    """
    repo = FeatureQASessionRepository(db, org_id=org.id)
    session = await repo.get_by_thread(channel, thread_ts)

    if session is None:
        return  # Not a Q&A thread

    if session.status != FeatureQAStatus.AWAITING_USER:
        return  # Session already resolved or errored

    logger.info("feature_qa_continue", session_id=str(session.id))

    thread_messages = await slack_client.conversations_replies(bot_token, channel, thread_ts)
    await _run_qa_agent(db, org, bot_token, session, thread_messages=thread_messages)


# ── Private helpers ────────────────────────────────────────────────


async def _run_qa_agent(
    db: AsyncSession,
    org: Organization,
    bot_token: str,
    session: FeatureQASession,
    thread_messages: list[dict[str, Any]] | None,
) -> None:
    """Run the Q&A agent and post its response to the Slack thread."""
    skill = load_skill(_SKILL_NAME)

    prompt = _build_qa_prompt(skill.prompt, session, thread_messages)

    token = create_internal_mcp_token(org.id)
    mcp = MCPServerConfig(
        backend_url=app_settings.mcp_backend_url,
        mcp_token=token,
        tool_names=["get_bud_context", "check_feature_exists", "get_features"],
    )

    result = await run_claude_code(
        prompt=prompt,
        working_dir=NO_REPO_CONTEXT,
        config=ClaudeRunnerConfig(max_turns=skill.max_turns, timeout_seconds=90, mcp=mcp),
    )

    if not result.success:
        await slack_client.chat_post_message(
            bot_token,
            session.channel,
            "⚠️ Couldn't look that up right now. Please try again shortly.",
            thread_ts=session.thread_ts,
        )
        session.status = FeatureQAStatus.ERRORED
        logger.warning("feature_qa_agent_failed", session_id=str(session.id), error=result.error)
        return

    response = parse_json_response(result.output)
    if response is None:
        await slack_client.chat_post_message(
            bot_token,
            session.channel,
            "⚠️ Couldn't parse that. Try rephrasing your question.",
            thread_ts=session.thread_ts,
        )
        session.status = FeatureQAStatus.ERRORED
        return

    action = response.get("action", "")
    data = response.get("data", {})

    if action == "answer":
        reply = await _build_answer_reply(db, org, data)
        await slack_client.chat_post_message(
            bot_token, session.channel, reply, thread_ts=session.thread_ts
        )
        session.status = FeatureQAStatus.RESOLVED

    elif action == "clarify":
        reply = format_clarify_reply(
            data.get("question", "Which one did you mean?"),
            data.get("candidates", []),
        )
        await slack_client.chat_post_message(
            bot_token, session.channel, reply, thread_ts=session.thread_ts
        )
        await FeatureQASessionRepository(db, org_id=org.id).update_context(
            session, {"candidates": data.get("candidates", [])}
        )

    elif action == "not_found":
        await slack_client.chat_post_message(
            bot_token,
            session.channel,
            data.get(
                "message",
                "I couldn't find a feature matching that description."
                " React 🧠 on your message to start intake.",
            ),
            thread_ts=session.thread_ts,
        )
        session.status = FeatureQAStatus.RESOLVED

    else:
        logger.warning("feature_qa_unknown_action", session_id=str(session.id), action=action)
        session.status = FeatureQAStatus.ERRORED

    logger.info("feature_qa_agent_completed", session_id=str(session.id), action=action)


def _parse_uuid(raw: str | None) -> uuid.UUID | None:
    """Best-effort UUID coercion — returns None for hallucinated agent IDs."""
    if not raw:
        return None
    try:
        return uuid.UUID(raw)
    except ValueError:
        return None


async def _build_answer_reply(
    db: AsyncSession,
    org: Organization,
    data: dict[str, Any],
) -> str:
    """Resolve a BUD or Feature by ID and format the reply string."""
    kind = data.get("kind", "bud")

    if kind == "bud":
        bud_id = _parse_uuid(data.get("id"))
        if bud_id is None:
            return "Found a match but couldn't load the BUD details. Check the dashboard."
        bud_repo = BUDRepository(db, org_id=org.id)
        bud = await bud_repo.get_by_id(bud_id)
        if bud is None:
            return "Found a match but couldn't load the BUD details. Check the dashboard."

        assignee: Any = None
        if bud.assignee_id:
            user_repo = UserRepository(db)
            assignee = await user_repo.get_by_id(bud.assignee_id)

        return format_bud_answer(bud, assignee, app_settings.frontend_url)

    feature_id = _parse_uuid(data.get("id"))
    if feature_id is None:
        return "Found a match but couldn't load the feature details."

    feature_repo = FeatureRepository(db, org_id=org.id)
    feature = await feature_repo.get_by_id(feature_id)
    if feature is None:
        return "Found a match but couldn't load the feature details."

    return format_feature_answer(feature)


def _build_qa_prompt(
    skill_prompt: str,
    session: FeatureQASession,
    thread_messages: list[dict[str, Any]] | None,
) -> str:
    """Build the agent prompt from the skill instructions and conversation context."""
    sections = [skill_prompt, "---\n\n## Conversation\n"]

    if thread_messages:
        msgs = thread_messages[-10:] if len(thread_messages) > 10 else thread_messages
        for msg in msgs:
            is_bot = bool(msg.get("bot_id"))
            user = msg.get("user", "unknown")
            text = msg.get("text", "")
            prefix = "[BOT]" if is_bot else "[REPLY]"
            sections.append(f"{prefix} {user}: {text}")
    else:
        question = _strip_bot_mention(session.original_question or "")
        sections.append(f"[QUESTION] {session.requester_slack_user_id}: {question}")

    if session.context:
        sections.append(f"\n## Prior candidates\n{session.context}")

    sections.append("\n---\n\nRespond with a single JSON object.")
    return "\n".join(sections)


def _strip_bot_mention(text: str) -> str:
    """Remove Slack bot mention tokens from text."""
    return _BOT_MENTION_RE.sub("", text).strip()
