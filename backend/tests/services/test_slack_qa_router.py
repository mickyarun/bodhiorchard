# Copyright 2025-2026 Arun Rajkumar
#
# Licensed under the Apache License, Version 2.0 (the "License").

"""Intent-classification contract for the Slack Q&A router.

The router is the cost / latency centre of the new Brain Q&A pipeline.
Two behaviours must hold:

1. **ACK short-circuit.** Pure acknowledgement replies must never
   spawn a Claude subprocess. Saving the ~1.5 s Haiku call (and its
   billing event) on every "thanks" is the headline win for the
   conversational tail of every thread.
2. **Label parsing is forgiving.** Haiku occasionally wraps a single
   label in quotes, code fences, or trailing punctuation. The parser
   must strip those and still land on the right :class:`QaIntent`.
   Anything truly unrecognised falls through to ``UNKNOWN`` (which
   the dispatcher routes to the safe EXPLAIN specialist) — never raise.

These tests stub ``run_claude_code`` so they're hermetic and cheap.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from app.services import slack_qa_router
from app.services.slack_qa_router import QaIntent, classify_qa_intent

# ── ACK short-circuit ────────────────────────────────────────────────


@pytest.mark.parametrize(
    "text",
    [
        "thanks",
        "Thanks!",
        "thank you",
        "ok",
        "OK!",
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
        "ty",
    ],
)
@pytest.mark.asyncio
async def test_ack_short_circuits_without_subprocess(text: str, monkeypatch: Any) -> None:
    """For pure-ack tokens the router must NOT call run_claude_code."""

    async def _explode(*a: Any, **kw: Any) -> Any:
        raise AssertionError(f"run_claude_code should not run for ack text {text!r}")

    monkeypatch.setattr(slack_qa_router, "run_claude_code", _explode)

    intent = await classify_qa_intent(
        question_text=text,
        thread_messages=None,
        session_context=None,
    )

    assert intent is QaIntent.ACK


@pytest.mark.asyncio
async def test_long_reply_starting_with_thanks_still_calls_classifier(
    monkeypatch: Any,
) -> None:
    """A four-word ceiling guards against false-positive acks.

    ``"thanks that's helpful, what about timeline?"`` is six words and
    must reach Haiku — the user is asking a follow-up, not closing the
    conversation.
    """
    called = {"yes": False}

    async def _record(*, prompt: str, **kw: Any) -> Any:
        called["yes"] = True
        return MagicMock(success=True, output="TIMELINE", error=None)

    monkeypatch.setattr(slack_qa_router, "run_claude_code", _record)

    intent = await classify_qa_intent(
        question_text="thanks that's helpful, what about timeline?",
        thread_messages=None,
        session_context=None,
    )

    assert called["yes"] is True, "long reply must reach Haiku"
    assert intent is QaIntent.TIMELINE


# ── Label parsing ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("TIMELINE", QaIntent.TIMELINE),
        ("timeline", QaIntent.TIMELINE),
        ("Timeline.", QaIntent.TIMELINE),
        ('"OWNERSHIP"', QaIntent.OWNERSHIP),
        ("```\nSTATUS\n```", QaIntent.STATUS),
        ("EXPLAIN ", QaIntent.EXPLAIN),
        ("DISAMBIGUATE", QaIntent.DISAMBIGUATE),
        ("UNKNOWN", QaIntent.UNKNOWN),
        # Junk falls through to UNKNOWN, never raises.
        ("", QaIntent.UNKNOWN),
        ("MAYBE_TIMELINE_OR_SOMETHING", QaIntent.UNKNOWN),
        ("here is your label: timeline", QaIntent.UNKNOWN),  # extra prose
    ],
)
@pytest.mark.asyncio
async def test_parses_haiku_label(raw: str, expected: QaIntent, monkeypatch: Any) -> None:
    """Forgiving label parser maps common Haiku quirks to the right intent."""

    async def _return(*, prompt: str, **kw: Any) -> Any:
        return MagicMock(success=True, output=raw, error=None)

    monkeypatch.setattr(slack_qa_router, "run_claude_code", _return)

    intent = await classify_qa_intent(
        question_text="when does it ship?",
        thread_messages=None,
        session_context=None,
    )
    assert intent is expected


@pytest.mark.asyncio
async def test_subprocess_failure_returns_unknown(monkeypatch: Any) -> None:
    """A Haiku subprocess failure must not propagate — UNKNOWN routes
    to the safe EXPLAIN specialist downstream."""

    async def _fail(*, prompt: str, **kw: Any) -> Any:
        return MagicMock(success=False, output="", error="boom")

    monkeypatch.setattr(slack_qa_router, "run_claude_code", _fail)

    intent = await classify_qa_intent(
        question_text="when does it ship?",
        thread_messages=None,
        session_context=None,
    )

    assert intent is QaIntent.UNKNOWN


# ── Prompt-shape contract ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_prior_candidates_surface_in_prompt(monkeypatch: Any) -> None:
    """When the session carries prior candidates, the Haiku prompt must
    include them so short follow-ups like 'timeline give me' can route
    correctly."""
    captured: dict[str, str] = {}

    async def _capture(*, prompt: str, **kw: Any) -> Any:
        captured["prompt"] = prompt
        return MagicMock(success=True, output="TIMELINE", error=None)

    monkeypatch.setattr(slack_qa_router, "run_claude_code", _capture)

    await classify_qa_intent(
        question_text="timeline give me",
        thread_messages=None,
        session_context={
            "candidates": [{"kind": "bud", "id": "u-1", "bud_number": 229, "title": "Demo"}]
        },
    )

    prompt = captured["prompt"]
    assert "[PRIOR_CANDIDATES]" in prompt
    assert "BUD-229" in prompt


@pytest.mark.asyncio
async def test_no_candidates_means_no_bud_reference(monkeypatch: Any) -> None:
    """No candidates → no BUD reference in the conversation section.

    Note: ``[PRIOR_CANDIDATES]`` itself appears in the skill body's
    examples block, so asserting on the literal marker would always
    succeed. The contract we care about is that no specific BUD number
    is injected when the session has no prior candidates.
    """
    captured: dict[str, str] = {}

    async def _capture(*, prompt: str, **kw: Any) -> Any:
        captured["prompt"] = prompt
        return MagicMock(success=True, output="EXPLAIN", error=None)

    monkeypatch.setattr(slack_qa_router, "run_claude_code", _capture)

    await classify_qa_intent(
        question_text="explain how X works",
        thread_messages=None,
        session_context=None,
    )

    # The Conversation section is appended after the skill body.
    conversation = captured["prompt"].split("## Conversation", 1)[-1]
    assert "BUD-" not in conversation
