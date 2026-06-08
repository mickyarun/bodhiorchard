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

Handles @mention and ❓-reaction events, classifies the user's intent
with a cheap Haiku router, and dispatches to the matching specialist
skill (bud-fact / explain / disambiguate). Acknowledgement replies
("thanks", "ok") short-circuit before any subprocess spawns.

Why intent routing instead of one mega-skill: the previous
``slack-feature-qa`` skill bundled nine distinct intent branches into
~12 KB of prompt; the model deliberated across all branches every
turn and stalled cold-cache runs at the 90 s timeout. Each specialist
prompt is < 2 KB and only loads the rules and MCP tools its intent
needs, dropping cold-cache p99 from > 89 s to ~7 s end-to-end.
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
from app.services.claude_errors import ClaudeErrorCode
from app.services.claude_runner import (
    NO_REPO_CONTEXT,
    ClaudeRunnerConfig,
    MCPServerConfig,
    run_claude_code,
)
from app.services.json_parser import parse_json_response
from app.services.skill_loader import Skill, load_skill
from app.services.slack_feature_qa_reply import (
    format_bud_answer,
    format_clarify_reply,
    format_feature_answer,
)
from app.services.slack_qa_router import QaIntent, classify_qa_intent

logger = structlog.get_logger(__name__)

_BOT_MENTION_RE = re.compile(r"<@[A-Z0-9]+>")

# Per-intent skill slug + MCP tool whitelist. Loaded once from file
# (specialists deliberately bypass the per-org ``agent_skills`` override
# path while the intent split rolls out — a follow-up wires Settings →
# Agent Prompts customisation back in via either four ``AgentType``
# values or per-slug overrides).
_SKILL_BY_INTENT: dict[QaIntent, str] = {
    QaIntent.TIMELINE: "slack-qa-bud-fact",
    QaIntent.OWNERSHIP: "slack-qa-bud-fact",
    QaIntent.STATUS: "slack-qa-bud-fact",
    QaIntent.EXPLAIN: "slack-qa-explain",
    QaIntent.DISAMBIGUATE: "slack-qa-disambiguate",
    # UNKNOWN falls through to EXPLAIN — broadest tool set, safest
    # default for any classifier miss.
    QaIntent.UNKNOWN: "slack-qa-explain",
}

_TOOLS_BY_INTENT: dict[QaIntent, list[str]] = {
    QaIntent.TIMELINE: ["get_bud_context", "get_features"],
    QaIntent.OWNERSHIP: ["get_bud_context", "get_features"],
    QaIntent.STATUS: ["get_bud_context", "get_features"],
    QaIntent.EXPLAIN: ["get_bud_context", "get_features", "check_feature_exists"],
    QaIntent.DISAMBIGUATE: ["get_bud_context", "get_features"],
    QaIntent.UNKNOWN: ["get_bud_context", "get_features", "check_feature_exists"],
}

# Hard ceiling on specialist agent loops. The mega-skill carried
# ``max_turns: 10`` from when it had to fan out across nine branches;
# the specialists complete a normal answer in 2-4 turns. Six gives
# headroom for one retry on a parse error without letting a runaway
# loop chew through 90 seconds.
_SPECIALIST_MAX_TURNS_CEILING = 6

# Floor on the same loop. Bud-fact needs at least one tool turn plus
# one answer-JSON turn; explain may issue up to three tool calls. Two
# is the smallest value that keeps any specialist functional, even if
# a future admin Settings edit tries to set ``max_turns: 1``.
_SPECIALIST_MAX_TURNS_FLOOR = 2

# Wall-clock cap on the specialist Claude subprocess. Down from the
# old 90 s — a healthy cold-cache run with a < 2 KB prompt completes
# in ~6 s, warm in ~3 s. 60 s catches genuine hangs without papering
# over them.
_SPECIALIST_TIMEOUT_SECONDS = 60

_ACK_REPLY = "Happy to help — ask anything else about this feature."


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

    # Ack so the thread shows activity while the agent runs (~5s of silence
    # otherwise looks frozen, especially after a clarify turn where the user
    # is actively waiting on a follow-up).
    await slack_client.chat_post_message(
        bot_token,
        channel,
        "🔍 Still looking that up...",
        thread_ts=thread_ts,
    )

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
    """Classify the Slack Q&A turn, dispatch to the matching specialist."""
    question_text = _latest_question_text(session, thread_messages)
    intent = await classify_qa_intent(
        question_text=question_text,
        thread_messages=thread_messages,
        session_context=session.context,
    )
    logger.info(
        "feature_qa_intent_routed",
        session_id=str(session.id),
        intent=intent.value,
    )

    # ACK short-circuits the LLM specialist entirely — post a canned
    # reply and leave the session open for the next real question.
    if intent == QaIntent.ACK:
        await slack_client.chat_post_message(
            bot_token, session.channel, _ACK_REPLY, thread_ts=session.thread_ts
        )
        return

    try:
        skill = load_skill(_SKILL_BY_INTENT[intent])
    except (FileNotFoundError, ValueError):
        logger.exception(
            "feature_qa_specialist_skill_load_failed",
            session_id=str(session.id),
            slug=_SKILL_BY_INTENT[intent],
        )
        await slack_client.chat_post_message(
            bot_token,
            session.channel,
            "⚠️ Couldn't look that up right now. Please try again shortly.",
            thread_ts=session.thread_ts,
        )
        session.status = FeatureQAStatus.ERRORED
        return

    bud_hint = _drill_down_bud_number(session.context)
    prompt = _build_qa_prompt(skill.prompt, session, thread_messages, bud_hint=bud_hint)

    token = create_internal_mcp_token(org.id)
    mcp = MCPServerConfig(
        backend_url=app_settings.mcp_backend_url,
        mcp_token=token,
        tool_names=_TOOLS_BY_INTENT[intent],
    )

    try:
        result = await run_claude_code(
            prompt=prompt,
            working_dir=NO_REPO_CONTEXT,
            config=ClaudeRunnerConfig(
                max_turns=_clamp_specialist_max_turns(skill),
                timeout_seconds=skill.timeout_or_default(_SPECIALIST_TIMEOUT_SECONDS),
                model=skill.model or None,
                mcp=mcp,
            ),
        )
    except Exception:
        # The subprocess layer can raise on asyncio cancellation, OS
        # fork failures, or runaway resource limits — none of those
        # should silently drop the user's thread reply. Surface a
        # consistent "try again" message and mark the session errored
        # so the next reply re-enters cleanly via ``continue_feature_qa``.
        logger.exception("feature_qa_specialist_raised", session_id=str(session.id))
        await slack_client.chat_post_message(
            bot_token,
            session.channel,
            "⚠️ Couldn't look that up right now. Please try again shortly.",
            thread_ts=session.thread_ts,
        )
        session.status = FeatureQAStatus.ERRORED
        return

    if not result.success:
        # error_max_turns means the model couldn't commit within its turn
        # budget — for the bud-fact specialist that's "no clear BUD found",
        # not a server crash. Surface the not_found copy and keep the
        # session AWAITING_USER so the user can clarify in the same thread.
        if result.error_code == ClaudeErrorCode.MAX_TURNS:
            logger.info(
                "feature_qa_specialist_max_turns_soft_fallback",
                session_id=str(session.id),
                intent=intent.value,
            )
            await slack_client.chat_post_message(
                bot_token,
                session.channel,
                "I couldn't find a BUD matching that. React 🧠 on the original"
                " message to start intake, or reply with a BUD number / title.",
                thread_ts=session.thread_ts,
            )
            return

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

    # Session stays AWAITING_USER across answer/summary/clarify/not_found —
    # the thread IS the conversation, so any later reply should re-enter
    # the agent. Only parse/agent failures terminate the session (ERRORED).
    if action == "answer":
        reply = await _build_answer_reply(db, org, data)
        await slack_client.chat_post_message(
            bot_token, session.channel, reply, thread_ts=session.thread_ts
        )

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

    elif action == "summary":
        text = data.get("text", "").strip()
        if not text:
            logger.warning("feature_qa_summary_empty", session_id=str(session.id))
            await slack_client.chat_post_message(
                bot_token,
                session.channel,
                "⚠️ Couldn't generate a summary. Try asking about one feature at a time.",
                thread_ts=session.thread_ts,
            )
        else:
            await slack_client.chat_post_message(
                bot_token, session.channel, text, thread_ts=session.thread_ts
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
    *,
    bud_hint: int | None = None,
) -> str:
    """Build the agent prompt from the skill instructions and conversation context.

    When ``bud_hint`` is set, the specialist sees a ``[HINT_BUD_NUMBER]``
    marker referencing the prior turn's matched BUD. The bud-fact
    specialist uses this to skip its initial keyword search and go
    straight to a targeted ``get_bud_context`` call — saves an LLM
    turn on every drill-down ("timeline give me", "who?").
    """
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

    if bud_hint is not None:
        sections.append(f"\n[HINT_BUD_NUMBER] BUD-{bud_hint:03d}")

    candidates_block = _format_prior_candidates_block(session.context, bud_hint)
    if candidates_block:
        sections.append(candidates_block)

    sections.append("\n---\n\nRespond with a single JSON object.")
    return "\n".join(sections)


def _format_prior_candidates_block(
    session_context: dict[str, Any] | None,
    bud_hint: int | None,
) -> str:
    """Render prior candidates as a typed list, not a raw Python dict repr.

    The previous code dumped ``session.context`` directly via f-string,
    which produced Python single-quoted dict syntax inside the prompt.
    That bloated cold-cache cost and the model would occasionally
    treat the repr as code. Two more fixes baked in here:

    * When ``bud_hint`` is set the bud-fact specialist already has the
      drill-down marker — repeating every candidate is noise, so we
      skip the block entirely.
    * Feature-only candidates render as titles; BUD candidates render
      as ``BUD-NNN — title``. Both shapes are what the specialists'
      examples already document.
    """
    if bud_hint is not None:
        return ""
    if not session_context:
        return ""
    candidates = session_context.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        return ""
    lines: list[str] = ["\n## Prior candidates"]
    for cand in candidates:
        if not isinstance(cand, dict):
            continue
        if cand.get("kind") == "bud":
            bud_number = cand.get("bud_number")
            title = cand.get("title", "")
            if isinstance(bud_number, int):
                lines.append(f"- BUD-{bud_number:03d} — {title}".rstrip(" —"))
        elif cand.get("kind") == "feature":
            title = cand.get("title", "")
            if isinstance(title, str) and title:
                lines.append(f"- {title}")
    return "\n".join(lines) if len(lines) > 1 else ""


def _strip_bot_mention(text: str) -> str:
    """Remove Slack bot mention tokens from text."""
    return _BOT_MENTION_RE.sub("", text).strip()


def _latest_question_text(
    session: FeatureQASession,
    thread_messages: list[dict[str, Any]] | None,
) -> str:
    """Pick the text the router should classify.

    On a fresh session the original question lives on the row; on
    continuation turns the last non-bot thread message is what matters.
    Falls through to the row's ``original_question`` if no human reply
    is in the tail (defensive — shouldn't happen because
    ``continue_feature_qa`` always re-fetches the thread first).
    """
    if thread_messages:
        for msg in reversed(thread_messages):
            if msg.get("bot_id"):
                continue
            text = (msg.get("text") or "").strip()
            if text:
                return _strip_bot_mention(text)
    return _strip_bot_mention(session.original_question or "")


def _drill_down_bud_number(session_context: dict[str, Any] | None) -> int | None:
    """Extract the BUD number to focus on from prior-turn candidates.

    Populated when a prior ``clarify`` turn stored its candidates in
    ``session.context['candidates']`` (a separate follow-up PR also
    seeds the same key when triage finds a duplicate, so the drill-down
    fast path fires there too). Prefer the first BUD candidate over
    feature-only candidates — BUDs carry the date / status / assignee
    fields the bud-fact specialist returns.
    """
    if not session_context:
        return None
    candidates = session_context.get("candidates")
    if not isinstance(candidates, list):
        return None
    for cand in candidates:
        if not isinstance(cand, dict):
            continue
        if cand.get("kind") != "bud":
            continue
        bud_number = cand.get("bud_number")
        if isinstance(bud_number, int):
            return bud_number
    return None


def _clamp_specialist_max_turns(skill: Skill) -> int:
    """Specialist agent loop ceiling.

    The .md frontmatter may carry ``max_turns: 4``; the ceiling caps
    any admin tuning at ``_SPECIALIST_MAX_TURNS_CEILING`` so a future
    Settings UI change can't accidentally restore the 10-turn loop
    behaviour that gave the mega-skill room to time out. The floor
    (``_SPECIALIST_MAX_TURNS_FLOOR``) guards the opposite extreme:
    a stray ``max_turns: 1`` would prevent the bud-fact specialist
    from emitting BOTH a tool call AND its answer JSON.
    """
    base = skill.max_turns if skill.max_turns > 0 else _SPECIALIST_MAX_TURNS_CEILING
    return min(max(_SPECIALIST_MAX_TURNS_FLOOR, base), _SPECIALIST_MAX_TURNS_CEILING)
