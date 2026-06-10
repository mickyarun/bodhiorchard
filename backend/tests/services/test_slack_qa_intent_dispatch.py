# Copyright 2025-2026 Arun Rajkumar
#
# Licensed under the Apache License, Version 2.0 (the "License").

"""Slack Q&A dispatch + one-CLI-session-per-thread wire-up.

Behaviours we guarantee won't regress:

1. **ACK never spawns a subprocess.** The mega-skill paid 12 s + the
   Sonnet cost for every "thanks". The ACK short-circuit must keep
   that path subprocess-free; it's the headline UX win for the
   conversational tail of every thread.
2. **Each non-ACK intent loads the right specialist + tool set.**
   The pipeline only works if (a) the router's label, (b) the skill
   loaded, and (c) the MCP tool whitelist passed to the subprocess
   are aligned.
3. **Drill-down hint flows end-to-end.** When ``session.context``
   carries a prior BUD candidate, the bud-fact specialist must
   receive a ``[HINT_BUD_NUMBER]`` marker so it can skip its initial
   keyword search.
4. **Soft vs hard specialist failure.** ``MAX_TURNS`` / ``TIMEOUT``
   surface the not_found copy and keep the session open; hard errors
   flip it to ERRORED.
5. **One CLI session per thread.** The first turn claims the row UUID
   with ``--session-id``; follow-ups resume it (no router, reply-only
   prompt, full tool union); a resume that can't answer falls back
   once to the full-parse pipeline with no session affinity; pure-ack
   follow-ups short-circuit before resuming; and ``_RESUME_MODEL`` must
   match the specialists' declared model.

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
from app.services.claude_errors import ClaudeErrorCode
from app.services.skill_loader import load_skill
from app.services.slack_feature_qa import (
    _ALL_QA_TOOLS,
    _SKILL_BY_INTENT,
    _TOOLS_BY_INTENT,
    _resume_qa_turn,
    _run_qa_agent,
    continue_feature_qa,
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

    async def _capture(token: str, channel: str, text: str, **kw: Any) -> dict[str, Any]:
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


# ── 4. Soft-fallback when the specialist can't commit ────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "soft_code",
    [ClaudeErrorCode.MAX_TURNS, ClaudeErrorCode.TIMEOUT],
)
async def test_soft_fallback_returns_not_found_message_not_errored(
    soft_code: ClaudeErrorCode,
    monkeypatch: Any,
    _silence_slack_posts: dict[str, list[tuple[str, str | None]]],
) -> None:
    """``MAX_TURNS`` and ``TIMEOUT`` both mean "the model couldn't commit
    within its budget" on a fact-lookup specialist — neither is a server
    crash. Surface the not_found copy, keep the session AWAITING_USER
    so the user can clarify in the same thread.

    Asserts by reply *identity* (against ``slack_feature_qa`` module
    constants), not substring on the copy, so copy edits don't break
    this regression pin."""

    async def _timeline_intent(**kw: Any) -> QaIntent:
        return QaIntent.TIMELINE

    monkeypatch.setattr(slack_feature_qa, "classify_qa_intent", _timeline_intent)

    async def _soft_fail(*, prompt: str, working_dir: str, config: Any) -> Any:
        return MagicMock(
            success=False,
            output="",
            error="soft fallback",
            error_code=soft_code,
        )

    monkeypatch.setattr(slack_feature_qa, "run_claude_code", _soft_fail)

    session = _make_session()
    await _run_qa_agent(
        MagicMock(), MagicMock(id=uuid.uuid4()), "bot-token", session, thread_messages=None
    )

    assert session.status == FeatureQAStatus.AWAITING_USER

    texts = [text for text, _ in _silence_slack_posts["posts"]]
    assert slack_feature_qa._BUD_NOT_FOUND_REPLY in texts, (
        f"expected the not_found reply constant, got posts={texts!r}"
    )
    assert slack_feature_qa._GENERIC_FAILURE_REPLY not in texts, (
        "must NOT post the generic server-error reply on a soft fallback"
    )


@pytest.mark.asyncio
async def test_hard_error_still_marks_session_errored(
    monkeypatch: Any,
    _silence_slack_posts: dict[str, list[tuple[str, str | None]]],
) -> None:
    """``BINARY_MISSING`` is a real server-side problem — the dispatcher
    must keep posting the generic reply and flipping the session to
    ERRORED so it shows up loudly in logs and metrics. Pins the
    not-soft side of the ``_SOFT_FALLBACK_ERROR_CODES`` split."""

    async def _timeline_intent(**kw: Any) -> QaIntent:
        return QaIntent.TIMELINE

    monkeypatch.setattr(slack_feature_qa, "classify_qa_intent", _timeline_intent)

    async def _hard_fail(*, prompt: str, working_dir: str, config: Any) -> Any:
        return MagicMock(
            success=False,
            output="",
            error="binary missing",
            error_code=ClaudeErrorCode.BINARY_MISSING,
        )

    monkeypatch.setattr(slack_feature_qa, "run_claude_code", _hard_fail)

    session = _make_session()
    await _run_qa_agent(
        MagicMock(), MagicMock(id=uuid.uuid4()), "bot-token", session, thread_messages=None
    )

    assert session.status == FeatureQAStatus.ERRORED

    texts = [text for text, _ in _silence_slack_posts["posts"]]
    assert slack_feature_qa._GENERIC_FAILURE_REPLY in texts
    assert slack_feature_qa._BUD_NOT_FOUND_REPLY not in texts


# ── 5. One CLI session per thread: claim on first turn, resume after ──


def _queue_runs(monkeypatch: Any, results: list[Any]) -> list[dict[str, Any]]:
    """Stub run_claude_code to return ``results`` in order, recording calls.

    Each captured record carries the prompt, the full config (so tests can
    assert ``cli_session_id`` / ``is_resume``), and the tool whitelist.
    """
    runs: list[dict[str, Any]] = []
    pending = list(results)

    async def _capture(*, prompt: str, working_dir: str, config: Any) -> Any:
        runs.append(
            {
                "prompt": prompt,
                "config": config,
                "tool_names": list(config.mcp.tool_names) if config.mcp else [],
            }
        )
        nxt = pending.pop(0)
        if isinstance(nxt, BaseException):
            raise nxt  # exercise the resume except-branch
        return nxt

    monkeypatch.setattr(slack_feature_qa, "run_claude_code", _capture)
    return runs


def _ok_result(action: str = "not_found") -> Any:
    return MagicMock(
        success=True,
        output=f'{{"action": "{action}", "data": {{"message": ""}}}}',
        error=None,
    )


def _fail_result(code: ClaudeErrorCode = ClaudeErrorCode.UNKNOWN) -> Any:
    return MagicMock(success=False, output="", error="boom", error_code=code)


def _no_router(monkeypatch: Any) -> list[bool]:
    """Replace the router with a tripwire — resume turns must NOT classify."""
    called: list[bool] = []

    async def _tripwire(**kw: Any) -> QaIntent:
        called.append(True)
        return QaIntent.UNKNOWN

    monkeypatch.setattr(slack_feature_qa, "classify_qa_intent", _tripwire)
    return called


@pytest.mark.asyncio
async def test_start_turn_claims_session_id_with_session_id_flag(
    monkeypatch: Any,
) -> None:
    """The first turn must pass ``cli_session_id`` (the row UUID) with
    ``is_resume=False`` so the CLI claims the namespace via ``--session-id``,
    letting every follow-up resume it."""

    async def _explain(**kw: Any) -> QaIntent:
        return QaIntent.EXPLAIN

    monkeypatch.setattr(slack_feature_qa, "classify_qa_intent", _explain)
    runs = _queue_runs(monkeypatch, [_ok_result("summary")])

    session = _make_session()
    await _run_qa_agent(
        MagicMock(),
        MagicMock(id=uuid.uuid4()),
        "bot-token",
        session,
        thread_messages=None,
        cli_session_id=str(session.id),
    )

    assert len(runs) == 1
    cfg = runs[0]["config"]
    assert cfg.cli_session_id == str(session.id)
    assert cfg.is_resume is False


@pytest.mark.asyncio
async def test_fallback_run_has_no_session_affinity(monkeypatch: Any) -> None:
    """When ``_run_qa_agent`` runs without a ``cli_session_id`` (the resume
    fallback), it must not claim any session — ``cli_session_id`` stays None."""

    async def _explain(**kw: Any) -> QaIntent:
        return QaIntent.EXPLAIN

    monkeypatch.setattr(slack_feature_qa, "classify_qa_intent", _explain)
    runs = _queue_runs(monkeypatch, [_ok_result("summary")])

    await _run_qa_agent(
        MagicMock(), MagicMock(id=uuid.uuid4()), "bot-token", _make_session(), thread_messages=None
    )

    cfg = runs[0]["config"]
    assert cfg.cli_session_id is None
    assert cfg.is_resume is False


@pytest.mark.asyncio
async def test_resume_turn_sends_only_reply_and_skips_router(monkeypatch: Any) -> None:
    """A follow-up resumes the thread's session: ``is_resume=True`` with the
    row UUID, the prompt carries ONLY the reply (no specialist skill body),
    the full QA tool union is allowed, and the router never runs."""
    router_calls = _no_router(monkeypatch)
    runs = _queue_runs(monkeypatch, [_ok_result("answer")])

    session = _make_session()
    await _resume_qa_turn(
        MagicMock(), MagicMock(id=uuid.uuid4()), "bot-token", session, "delivery date?"
    )

    assert router_calls == [], "resume must NOT re-run the intent router"
    assert len(runs) == 1
    cfg = runs[0]["config"]
    assert cfg.is_resume is True
    assert cfg.cli_session_id == str(session.id)
    assert sorted(runs[0]["tool_names"]) == sorted(_ALL_QA_TOOLS)
    prompt = runs[0]["prompt"]
    assert "delivery date?" in prompt
    # No specialist skill body is re-sent on resume — it's already in
    # the resumed conversation. The skill headings are the cheap tell.
    assert "# Slack BUD Fact Lookup" not in prompt
    assert "# Slack Feature Explain" not in prompt


@pytest.mark.asyncio
async def test_resume_failure_falls_back_to_full_pipeline(monkeypatch: Any) -> None:
    """If resume can't produce an answer (e.g. the session file is gone),
    fall back once to the full-parse pipeline: a SECOND run with
    ``is_resume=False`` that DOES route, and the reply still lands."""

    async def _timeline(**kw: Any) -> QaIntent:
        return QaIntent.TIMELINE

    monkeypatch.setattr(slack_feature_qa, "classify_qa_intent", _timeline)

    async def _replies(token: str, channel: str, thread_ts: str) -> list[dict[str, Any]]:
        return [{"user": "U777", "text": "delivery date?"}]

    monkeypatch.setattr(slack_client, "conversations_replies", _replies)
    runs = _queue_runs(monkeypatch, [_fail_result(), _ok_result("answer")])

    session = _make_session()
    await _resume_qa_turn(
        MagicMock(), MagicMock(id=uuid.uuid4()), "bot-token", session, "delivery date?"
    )

    assert len(runs) == 2, "resume failure must trigger exactly one fallback run"
    assert runs[0]["config"].is_resume is True
    assert runs[1]["config"].is_resume is False
    assert runs[1]["config"].cli_session_id is None


@pytest.mark.asyncio
async def test_triage_seeded_handover_resume_miss_builds_hint(monkeypatch: Any) -> None:
    """The triage→Q&A seam: a session seeded with ``candidates`` but no prior
    CLI turn. The first reply's resume misses (no session file), and the
    fallback full-parse must build ``[HINT_BUD_NUMBER]`` from the seeded
    candidate so the answer stays grounded in the right BUD."""

    async def _timeline(**kw: Any) -> QaIntent:
        return QaIntent.TIMELINE

    monkeypatch.setattr(slack_feature_qa, "classify_qa_intent", _timeline)

    async def _replies(token: str, channel: str, thread_ts: str) -> list[dict[str, Any]]:
        return [{"user": "U777", "text": "delivery date?"}]

    monkeypatch.setattr(slack_client, "conversations_replies", _replies)
    runs = _queue_runs(monkeypatch, [_fail_result(), _ok_result("answer")])

    session = _make_session(
        context={
            "candidates": [{"kind": "bud", "id": "u-1", "bud_number": 17, "title": "Masking"}]
        }
    )
    await _resume_qa_turn(
        MagicMock(), MagicMock(id=uuid.uuid4()), "bot-token", session, "delivery date?"
    )

    fallback_prompt = runs[1]["prompt"]
    conversation = fallback_prompt.split("## Conversation", 1)[-1]
    assert "[HINT_BUD_NUMBER]" in conversation
    assert "BUD-017" in conversation


@pytest.mark.asyncio
async def test_continue_ack_short_circuits_before_resume(
    monkeypatch: Any,
    _silence_slack_posts: dict[str, list[tuple[str, str | None]]],
) -> None:
    """A pure-ack thread reply ("thanks") posts the canned reply and never
    resumes the session — no subprocess, no router."""
    router_calls = _no_router(monkeypatch)
    runs = _queue_runs(monkeypatch, [])

    session = _make_session()
    repo = MagicMock()

    async def _get(channel: str, thread_ts: str) -> Any:
        return session

    repo.get_by_thread = _get
    monkeypatch.setattr(slack_feature_qa, "FeatureQASessionRepository", lambda db, *, org_id: repo)

    await continue_feature_qa(
        MagicMock(),
        MagicMock(id=uuid.uuid4()),
        "bot-token",
        "C123",
        "1780000000.0001",
        "thanks",
    )

    assert runs == [], "ack must not spawn a subprocess"
    assert router_calls == [], "ack must not run the router"
    texts = [text for text, _ in _silence_slack_posts["posts"]]
    assert slack_feature_qa._ACK_REPLY in texts


@pytest.mark.asyncio
async def test_continue_non_ack_resumes(
    monkeypatch: Any,
) -> None:
    """A non-ack reply on an active session resumes (``is_resume=True``) and
    does NOT re-route through the intent classifier."""
    router_calls = _no_router(monkeypatch)
    runs = _queue_runs(monkeypatch, [_ok_result("answer")])

    session = _make_session()
    repo = MagicMock()

    async def _get(channel: str, thread_ts: str) -> Any:
        return session

    repo.get_by_thread = _get
    monkeypatch.setattr(slack_feature_qa, "FeatureQASessionRepository", lambda db, *, org_id: repo)

    await continue_feature_qa(
        MagicMock(),
        MagicMock(id=uuid.uuid4()),
        "bot-token",
        "C123",
        "1780000000.0001",
        "what's the delivery date?",
    )

    assert router_calls == []
    assert len(runs) == 1
    assert runs[0]["config"].is_resume is True


@pytest.mark.asyncio
async def test_resume_parse_failure_errors_without_fallback(
    monkeypatch: Any,
    _silence_slack_posts: dict[str, list[tuple[str, str | None]]],
) -> None:
    """A resume that succeeds at the subprocess level but returns
    unparseable output must post the parse-failure copy and flip the
    session to ERRORED — and must NOT trigger a second (fallback) run.
    Pins that the fallback fires on subprocess failure, not on bad JSON."""
    _no_router(monkeypatch)
    unparseable = MagicMock(success=True, output="not json at all", error=None)
    runs = _queue_runs(monkeypatch, [unparseable])

    session = _make_session()
    await _resume_qa_turn(
        MagicMock(), MagicMock(id=uuid.uuid4()), "bot-token", session, "delivery date?"
    )

    assert len(runs) == 1, "a parse failure is not a resume failure — no fallback run"
    assert session.status == FeatureQAStatus.ERRORED
    texts = [text for text, _ in _silence_slack_posts["posts"]]
    assert slack_feature_qa._PARSE_FAILURE_REPLY in texts


@pytest.mark.asyncio
async def test_resume_subprocess_raises_falls_back(monkeypatch: Any) -> None:
    """If the resume subprocess *raises* (not just returns failure), the
    except-branch must swallow-then-fall-back — one fresh full-parse run
    that still lands a reply. Exercises the ``result is None`` path."""

    async def _timeline(**kw: Any) -> QaIntent:
        return QaIntent.TIMELINE

    monkeypatch.setattr(slack_feature_qa, "classify_qa_intent", _timeline)

    async def _replies(token: str, channel: str, thread_ts: str) -> list[dict[str, Any]]:
        return [{"user": "U777", "text": "delivery date?"}]

    monkeypatch.setattr(slack_client, "conversations_replies", _replies)
    runs = _queue_runs(monkeypatch, [RuntimeError("subprocess died"), _ok_result("answer")])

    session = _make_session()
    await _resume_qa_turn(
        MagicMock(), MagicMock(id=uuid.uuid4()), "bot-token", session, "delivery date?"
    )

    assert len(runs) == 2, "a raised resume must still fall back to one full-parse run"
    assert runs[1]["config"].is_resume is False


def test_resume_model_matches_specialist_declared_model() -> None:
    """``_RESUME_MODEL`` must equal the model the QA specialists declare,
    or a resumed turn would switch models mid-conversation. Loads the real
    specialist skills so a frontmatter edit that moves a specialist off
    Sonnet fails here loudly instead of silently drifting."""
    for slug in set(_SKILL_BY_INTENT.values()):
        skill = load_skill(slug)
        assert skill.model == slack_feature_qa._RESUME_MODEL, (
            f"specialist {slug!r} declares model {skill.model!r}, "
            f"but _RESUME_MODEL is {slack_feature_qa._RESUME_MODEL!r} — they must match"
        )
