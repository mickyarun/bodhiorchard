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

"""Slack Q&A intent router.

Replaces the single Swiss-army-knife ``slack-feature-qa`` skill with a
two-step classification flow:

1. A cheap local regex catches pure acknowledgement replies ("thanks",
   "ok", "got it") and returns ``QaIntent.ACK`` without spawning any
   Claude subprocess at all — saves both seconds and tokens.
2. Everything else fires a tiny Haiku call (~400-char prompt,
   ``max_turns=1``, no MCP tools) that returns a single uppercase
   label. The label is mapped to one of the intent-specific specialist
   skills in ``slack_feature_qa._run_qa_agent``.

The mega-skill stalled cold-cache runs at the 90 s timeout because the
model deliberated over nine intent branches before its first tool call.
Splitting the routing decision out and letting each specialist start
from a small focused prompt drops that cold-cache time to ~7 s
end-to-end (Haiku 1.5 s + Sonnet specialist 6 s).
"""

import re
from enum import StrEnum
from typing import Any

import structlog

from app.models.organization import Organization
from app.services.ai_runner import run_agent
from app.services.claude_runner import (
    NO_REPO_CONTEXT,
    ClaudeRunnerConfig,
)
from app.services.skill_loader import load_skill

logger = structlog.get_logger(__name__)

_ROUTER_SKILL_SLUG = "slack-qa-router"

# Hard cap on the number of recent thread messages we hand to the
# classifier. The router only needs the latest reply plus a glimpse of
# what the bot last said — more than that bloats the Haiku prompt
# without improving routing accuracy.
_MAX_THREAD_TAIL = 3

# Hard cap on prior-candidate hints. Three is plenty: the disambiguation
# specialist itself enforces its own 5-candidate ceiling, and the
# router only needs to know IF a drill-down anchor exists — not the
# full list.
_MAX_CANDIDATE_HINTS = 3


class QaIntent(StrEnum):
    """One of the seven labels the router can emit.

    ``UNKNOWN`` is the fall-through — the dispatcher routes it to the
    EXPLAIN specialist (broadest tool set, safest default for
    questions whose intent we couldn't pin down).
    """

    TIMELINE = "TIMELINE"
    OWNERSHIP = "OWNERSHIP"
    STATUS = "STATUS"
    EXPLAIN = "EXPLAIN"
    DISAMBIGUATE = "DISAMBIGUATE"
    ACK = "ACK"
    UNKNOWN = "UNKNOWN"


# Pure-acknowledgement replies — short tokens or two-word phrases that
# carry no question content. Matched case-insensitively after stripping
# punctuation and collapsing whitespace. Kept deliberately small:
# anything longer needs the LLM to disambiguate "thanks for the dates"
# (still a question follow-up) from "thanks" (a pure ack). The four-word
# ceiling enforced in ``_is_pure_ack`` is the second guard.
_ACK_PHRASES: frozenset[str] = frozenset(
    {
        "thanks",
        "thank you",
        "thanks!",
        "ty",
        "ok",
        "okay",
        "k",
        "kk",
        "got it",
        "cool",
        "great",
        "perfect",
        "nice",
        "awesome",
        "cheers",
        "ack",
    }
)

_PUNCT_RE = re.compile(r"[^\w\s]")
_WS_RE = re.compile(r"\s+")


def _normalise_for_ack(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    no_punct = _PUNCT_RE.sub(" ", text.lower())
    return _WS_RE.sub(" ", no_punct).strip()


def _is_pure_ack(text: str) -> bool:
    """Return True when ``text`` is a bare acknowledgement reply.

    Two gates:

    * The normalised text must be in the curated ack phrase set.
    * The original text must contain ≤ 4 whitespace-separated tokens.
      A four-word ceiling is conservative — "thanks that's helpful"
      still looks like an ack but might preface a follow-up; sending
      it through the LLM is cheaper insurance than mis-classifying.
    """
    normalised = _normalise_for_ack(text)
    if not normalised:
        return False
    if len(normalised.split()) > 4:
        return False
    return normalised in _ACK_PHRASES


def is_acknowledgement(text: str) -> bool:
    """Public wrapper around the local ack check.

    Exposed so the Slack Q&A service can short-circuit pure-ack thread
    replies ("thanks", "ok") before resuming the CLI session — without
    spawning a subprocess and without importing a private symbol.
    """
    return _is_pure_ack(text)


def _format_thread_tail(thread_messages: list[dict[str, Any]] | None) -> str:
    """Render the last few thread messages for the router prompt."""
    if not thread_messages:
        return ""
    tail = thread_messages[-_MAX_THREAD_TAIL:]
    lines: list[str] = []
    for msg in tail:
        is_bot = bool(msg.get("bot_id"))
        prefix = "[BOT]" if is_bot else "[REPLY]"
        text = (msg.get("text") or "").strip()
        if text:
            lines.append(f"{prefix} {text}")
    return "\n".join(lines)


def _format_prior_candidates(session_context: dict[str, Any] | None) -> str:
    """Render `[PRIOR_CANDIDATES]` hint for drill-down classification.

    The QA agent stores past ``clarify`` candidates (and the duplicate
    seed planted by triage) under ``session.context["candidates"]``.
    Surface a compact summary so the classifier can recognise short
    follow-ups like *"timeline give me"* as TIMELINE-on-the-prior-BUD
    rather than UNKNOWN.
    """
    if not session_context:
        return ""
    candidates = session_context.get("candidates")
    if not candidates:
        return ""
    refs: list[str] = []
    for cand in candidates[:_MAX_CANDIDATE_HINTS]:
        if not isinstance(cand, dict):
            continue
        bud_number = cand.get("bud_number")
        if isinstance(bud_number, int):
            refs.append(f"BUD-{bud_number:03d}")
        else:
            title = cand.get("title")
            if isinstance(title, str) and title:
                refs.append(title)
    if not refs:
        return ""
    return "[PRIOR_CANDIDATES] " + ", ".join(refs)


def _build_router_prompt(
    skill_prompt: str,
    question_text: str,
    thread_messages: list[dict[str, Any]] | None,
    session_context: dict[str, Any] | None,
) -> str:
    """Assemble the Haiku prompt: skill body + thread snapshot."""
    sections: list[str] = [skill_prompt.strip(), "---", "## Conversation"]
    tail = _format_thread_tail(thread_messages)
    if tail:
        sections.append(tail)
    else:
        sections.append(f"[QUESTION] {question_text.strip()}")
    candidates = _format_prior_candidates(session_context)
    if candidates:
        sections.append(candidates)
    sections.extend(["---", "Return exactly one label as bare uppercase text."])
    return "\n\n".join(sections)


def _parse_label(raw: str) -> QaIntent:
    """Coerce the model's reply to a ``QaIntent`` member.

    Defensive on purpose: even with a one-turn ``max_turns`` cap and a
    "bare label only" instruction, models occasionally wrap the output
    in code fences, quotes, or trailing periods. Strip everything that
    isn't an A-Z character, then match against the enum. Anything else
    falls through to ``UNKNOWN``, which the dispatcher routes to EXPLAIN.
    """
    if not raw:
        return QaIntent.UNKNOWN
    cleaned = re.sub(r"[^A-Za-z]", "", raw).upper()
    try:
        return QaIntent(cleaned)
    except ValueError:
        return QaIntent.UNKNOWN


async def classify_qa_intent(
    *,
    question_text: str,
    thread_messages: list[dict[str, Any]] | None,
    session_context: dict[str, Any] | None,
    org: Organization | None = None,
) -> QaIntent:
    """Classify a Slack Q&A turn into a single :class:`QaIntent`.

    Local ack regex first; falls back to a one-turn Haiku call when the
    reply isn't a pure acknowledgement. The function NEVER raises — a
    subprocess failure logs and returns ``UNKNOWN`` so the dispatcher
    can still route to the safe EXPLAIN specialist.
    """
    # 1. Local ack short-circuit: no LLM, no subprocess, no cost.
    if _is_pure_ack(question_text):
        return QaIntent.ACK

    # 2. Otherwise call the Haiku classifier.
    try:
        skill = load_skill(_ROUTER_SKILL_SLUG)
    except (FileNotFoundError, ValueError):
        logger.exception("slack_qa_router_skill_load_failed", slug=_ROUTER_SKILL_SLUG)
        return QaIntent.UNKNOWN

    prompt = _build_router_prompt(skill.prompt, question_text, thread_messages, session_context)

    try:
        result = await run_agent(
            org,
            prompt,
            NO_REPO_CONTEXT,
            ClaudeRunnerConfig(
                max_turns=skill.max_turns or 1,
                timeout_seconds=skill.timeout_or_default(10),
                model=skill.model or "haiku",
                mcp=None,
            ),
        )
    except Exception:
        # Honour the "NEVER raises" contract in this function's docstring.
        # The subprocess layer can throw on rare conditions (asyncio
        # timeouts, OS-level fork failures, credential expiry); falling
        # through to UNKNOWN keeps the thread alive via the EXPLAIN
        # specialist instead of letting the exception bubble up and
        # silently drop the user's reply.
        logger.exception("slack_qa_router_classify_raised")
        return QaIntent.UNKNOWN

    if not result.success:
        logger.warning(
            "slack_qa_router_classify_failed",
            error=result.error,
            error_code=getattr(result, "error_code", None),
        )
        return QaIntent.UNKNOWN

    intent = _parse_label(result.output)
    logger.info(
        "slack_qa_router_classified",
        intent=intent.value,
        raw_output_len=len(result.output or ""),
    )
    return intent
