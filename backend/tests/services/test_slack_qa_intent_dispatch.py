# Copyright 2025-2026 Arun Rajkumar
#
# Licensed under the Apache License, Version 2.0 (the "License").

"""Intent → specialist wire-up in ``_run_qa_agent``.

Three behaviours we need to guarantee won't regress:

1. **ACK never spawns a subprocess.** The mega-skill paid 12 s + the
   Sonnet cost for every "thanks". The ACK short-circuit must keep
   that path subprocess-free; it's the headline UX win for the
   conversational tail of every thread.
2. **Each non-ACK intent loads the right specialist + tool set.**
   The pipeline only works if (a) the router's label, (b) the skill
   loaded, and (c) the MCP tool whitelist passed to the subprocess
   are aligned. A wrong tool list silently breaks the specialist —
   e.g., the disambiguate skill calling ``check_feature_exists``
   when the dispatcher forgot to whitelist it.
3. **Drill-down hint flows end-to-end.** When ``session.context``
   carries a prior BUD candidate, the bud-fact specialist must
   receive a ``[HINT_BUD_NUMBER]`` marker so it can skip its initial
   keyword search and answer in one fewer turn.

All Claude calls and Slack posts are stubbed — these tests are
hermetic and cheap.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.models.feature_qa_session import FeatureQAStatus
from app.services import slack_client, slack_feature_qa
from app.services.slack_feature_qa import (
    _SKILL_BY_INTENT,
    _TOOLS_BY_INTENT,
    _run_qa_agent,
)
from app.services.slack_qa_router import QaIntent


def _make_session(
    context: dict[str, Any] | None = None, original_question: str = "anything"
) -> MagicMock:
    """A FeatureQASession-shaped mock with the fields the dispatcher reads."""
    return MagicMock(
        id=uuid.uuid4(),
        channel="C123",
        thread_ts="1780000000.0001",
        requester_slack_user_id="U777",
        original_question=original_question,
        context=context,
        status=FeatureQAStatus.AWAITING_USER,
    )


@pytest.fixture(autouse=True)
def _silence_slack_posts(monkeypatch: Any) -> dict[str, list[str]]:
    """Capture chat_post_message calls without hitting Slack."""
    posts: list[tuple[str, str | None]] = []

    async def _capture(
        token: str, channel: str, text: str, **kw: Any
    ) -> dict[str, Any]:
        posts.append((text, kw.get("thread_ts")))
        return {"ok": True}

    monkeypatch.setattr(slack_client, "chat_post_message", _capture)
    return {"posts": posts}  # type: ignore[dict-item]


@pytest.fixture
def captured_runs(monkeypatch: Any) -> list[dict[str, Any]]:
    """Capture every run_claude_code call into a list of records."""
    runs: list[dict[str, Any]] = []

    async def _capture(*, prompt: str, working_dir: str, config: Any) -> Any:
        runs.append(
            {
                "prompt": prompt,
                "config": config,
                "tool_names": list(config.mcp.tool_names) if config.mcp else [],
            }
        )
        return MagicMock(
            success=True, output='{"action": "not_found", "data": {"message": ""}}', error=None
        )

    monkeypatch.setattr(slack_feature_qa, "run_claude_code", _capture)
    return runs


# ── 1. ACK short-circuits ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ack_does_not_spawn_subprocess(
    monkeypatch: Any, captured_runs: list[dict[str, Any]]
) -> None:
    """A pure-ack reply must short-circuit before any subprocess runs."""

    async def _ack_intent(**kw: Any) -> QaIntent:
        return QaIntent.ACK

    monkeypatch.setattr(slack_feature_qa, "classify_qa_intent", _ack_intent)

    session = _make_session()
    await _run_qa_agent(
        MagicMock(), MagicMock(id=uuid.uuid4()), "bot-token", session, thread_messages=None
    )

    assert captured_runs == [], "ACK must NOT call run_claude_code — that's the latency / cost win"


# ── 2. Each intent loads the right specialist + tool set ────────────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "intent",
    [
        QaIntent.TIMELINE,
        QaIntent.OWNERSHIP,
        QaIntent.STATUS,
        QaIntent.EXPLAIN,
        QaIntent.DISAMBIGUATE,
        QaIntent.UNKNOWN,
    ],
)
async def test_intent_routes_to_expected_skill_and_tools(
    intent: QaIntent, monkeypatch: Any, captured_runs: list[dict[str, Any]]
) -> None:
    """Each classified intent must load the documented specialist slug
    and pass its MCP tool whitelist to the subprocess."""

    async def _force_intent(**kw: Any) -> QaIntent:
        return intent

    monkeypatch.setattr(slack_feature_qa, "classify_qa_intent", _force_intent)

    session = _make_session()
    await _run_qa_agent(
        MagicMock(), MagicMock(id=uuid.uuid4()), "bot-token", session, thread_messages=None
    )

    assert len(captured_runs) == 1, "non-ACK intents must spawn one subprocess"
    captured = captured_runs[0]
    assert sorted(captured["tool_names"]) == sorted(_TOOLS_BY_INTENT[intent])
    # Pin the SPECIFIC specialist heading, not a loose substring. Each
    # specialist's .md file opens with its own ``# Slack …`` heading,
    # and those headings are distinct per intent.
    specialist_heading = {
        "slack-qa-bud-fact": "# Slack BUD Fact Lookup",
        "slack-qa-explain": "# Slack Feature Explain",
        "slack-qa-disambiguate": "# Slack Disambiguation Specialist",
    }[_SKILL_BY_INTENT[intent]]
    assert specialist_heading in captured["prompt"], (
        f"expected specialist heading {specialist_heading!r} not in prompt"
    )


@pytest.mark.asyncio
async def test_specialist_max_turns_clamped(
    monkeypatch: Any, captured_runs: list[dict[str, Any]]
) -> None:
    """The dispatcher must clamp max_turns at the specialist ceiling
    regardless of what the skill frontmatter declares."""

    async def _explain_intent(**kw: Any) -> QaIntent:
        return QaIntent.EXPLAIN

    monkeypatch.setattr(slack_feature_qa, "classify_qa_intent", _explain_intent)

    session = _make_session()
    await _run_qa_agent(
        MagicMock(), MagicMock(id=uuid.uuid4()), "bot-token", session, thread_messages=None
    )

    config = captured_runs[0]["config"]
    assert 1 <= config.max_turns <= slack_feature_qa._SPECIALIST_MAX_TURNS_CEILING


# ── 3. Drill-down hint flows end-to-end ──────────────────────────────


@pytest.mark.asyncio
async def test_drill_down_injects_bud_hint_into_specialist_prompt(
    monkeypatch: Any, captured_runs: list[dict[str, Any]]
) -> None:
    """When session.context.candidates carries a BUD, the bud-fact
    specialist must receive a ``[HINT_BUD_NUMBER]`` marker so it can
    skip its initial keyword search."""

    async def _timeline_intent(**kw: Any) -> QaIntent:
        return QaIntent.TIMELINE

    monkeypatch.setattr(slack_feature_qa, "classify_qa_intent", _timeline_intent)

    session = _make_session(
        context={"candidates": [{"kind": "bud", "id": "u-1", "bud_number": 229, "title": "Demo"}]}
    )
    await _run_qa_agent(
        MagicMock(), MagicMock(id=uuid.uuid4()), "bot-token", session, thread_messages=None
    )

    # Inspect only the appended Conversation section — the bud-fact
    # skill body itself mentions ``[HINT_BUD_NUMBER]`` in its
    # instructions, so we can't assert against the whole prompt.
    conversation = captured_runs[0]["prompt"].split("## Conversation", 1)[-1]
    assert "[HINT_BUD_NUMBER]" in conversation
    assert "BUD-229" in conversation


@pytest.mark.asyncio
async def test_no_drill_down_when_candidates_are_feature_only(
    monkeypatch: Any, captured_runs: list[dict[str, Any]]
) -> None:
    """Feature-only candidates carry no `bud_number` — no hint should
    leak into the specialist prompt's Conversation section."""

    async def _timeline_intent(**kw: Any) -> QaIntent:
        return QaIntent.TIMELINE

    monkeypatch.setattr(slack_feature_qa, "classify_qa_intent", _timeline_intent)

    session = _make_session(
        context={"candidates": [{"kind": "feature", "id": "u-1", "title": "Demo feature"}]}
    )
    await _run_qa_agent(
        MagicMock(), MagicMock(id=uuid.uuid4()), "bot-token", session, thread_messages=None
    )

    conversation = captured_runs[0]["prompt"].split("## Conversation", 1)[-1]
    assert "[HINT_BUD_NUMBER]" not in conversation
