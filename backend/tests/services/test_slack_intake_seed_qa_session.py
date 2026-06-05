# Copyright 2025-2026 Arun Rajkumar
#
# Licensed under the Apache License, Version 2.0 (the "License").

"""Thread continuation after a triage duplicate match.

When ``_verify_duplicate_with_llm`` confirms a match, the triage flow
posts an "already tracked" reply and marks itself ``REJECTED``. Before
this fix the thread was dead at that point — neither
``continue_triage`` (which filters to ``INTERVIEWING / CHECKING``) nor
``continue_feature_qa`` (which needs a ``FeatureQASession`` to exist)
would pick up a reply, so user follow-ups in image-3 / image-4 of the
bug report were silently dropped.

This pins the new behaviour:

1. After a duplicate match, a ``FeatureQASession`` is opened on the
   same ``(channel, thread_ts)`` with the matched candidate stored in
   ``context.candidates`` (same shape ``clarify`` already uses, so the
   Q&A skill's "Drill-down on the prior result" branch recognises it).
2. If a Q&A session already exists for the thread, the helper is a
   no-op — we never try to violate the unique-on-thread constraint.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.models.feature_qa_session import FeatureQASession, FeatureQAStatus
from app.repositories.feature_qa_session import FeatureQASessionRepository
from app.services.slack_intake import _seed_qa_session_for_match


def _fake_triage_session() -> MagicMock:
    """A TriageSession-shaped mock with the attributes the helper reads."""
    return MagicMock(
        id=uuid.uuid4(),
        slack_channel="C123",
        thread_ts="1700000000.0001",
        requester_slack_id="U777",
    )


def _fake_bud_match() -> MagicMock:
    """A BUDDocument-shaped mock for the match argument."""
    return MagicMock(
        id=uuid.uuid4(),
        bud_number=21,
        title="Add Bank A, Bank B & Bank C support",
    )


def _fake_feature_match() -> MagicMock:
    return MagicMock(
        id=uuid.uuid4(),
        feature_title="Patient lookup integration",
    )


@pytest.mark.asyncio
async def test_seeds_qa_session_for_bud_match(monkeypatch: Any) -> None:
    """Helper opens a FeatureQASession with the BUD candidate stored
    in the same shape ``clarify`` emits, so the Q&A skill's Follow-up
    Turns branch can drill down on it."""
    triage = _fake_triage_session()
    bud = _fake_bud_match()
    org = MagicMock(id=uuid.uuid4())

    async def _no_existing(self: Any, channel: str, thread_ts: str) -> None:
        return None

    captured: dict[str, Any] = {}

    async def _capture_create(self: Any, entity: FeatureQASession) -> FeatureQASession:
        captured["entity"] = entity
        return entity

    monkeypatch.setattr(FeatureQASessionRepository, "get_by_thread", _no_existing)
    monkeypatch.setattr(FeatureQASessionRepository, "create", _capture_create)

    await _seed_qa_session_for_match(
        MagicMock(), org, triage, "bud", bud, query_text="Yapily Ireland banks"
    )

    qa_session = captured["entity"]
    assert isinstance(qa_session, FeatureQASession)
    assert qa_session.channel == triage.slack_channel
    assert qa_session.thread_ts == triage.thread_ts
    assert qa_session.requester_slack_user_id == triage.requester_slack_id
    assert qa_session.status == FeatureQAStatus.AWAITING_USER
    assert qa_session.original_question == "Yapily Ireland banks"

    candidates = (qa_session.context or {}).get("candidates", [])
    assert len(candidates) == 1
    candidate = candidates[0]
    # Same keys ``clarify`` produces — the Q&A skill already knows
    # how to read this shape on a follow-up turn.
    assert candidate == {
        "kind": "bud",
        "id": str(bud.id),
        "bud_number": bud.bud_number,
        "title": bud.title,
    }


@pytest.mark.asyncio
async def test_seeds_qa_session_for_feature_match(monkeypatch: Any) -> None:
    """Feature matches go through the same path with a feature-shaped
    candidate (no ``bud_number``, ``feature_title`` instead of ``title``)."""
    triage = _fake_triage_session()
    feature = _fake_feature_match()
    org = MagicMock(id=uuid.uuid4())

    async def _no_existing(self: Any, channel: str, thread_ts: str) -> None:
        return None

    captured: dict[str, Any] = {}

    async def _capture_create(self: Any, entity: FeatureQASession) -> FeatureQASession:
        captured["entity"] = entity
        return entity

    monkeypatch.setattr(FeatureQASessionRepository, "get_by_thread", _no_existing)
    monkeypatch.setattr(FeatureQASessionRepository, "create", _capture_create)

    await _seed_qa_session_for_match(
        MagicMock(), org, triage, "feature", feature, query_text="Patient name in dentally"
    )

    candidates = (captured["entity"].context or {}).get("candidates", [])
    assert candidates == [
        {"kind": "feature", "id": str(feature.id), "title": feature.feature_title}
    ]


@pytest.mark.asyncio
async def test_skips_create_when_qa_session_already_exists(monkeypatch: Any) -> None:
    """Idempotent: if a Q&A session already covers this thread (rare,
    but possible when the user @-mentioned the bot before reacting 🧠),
    don't try to insert another — the unique constraint would reject."""
    triage = _fake_triage_session()
    bud = _fake_bud_match()

    existing = MagicMock(spec=FeatureQASession)

    async def _has_existing(self: Any, channel: str, thread_ts: str) -> Any:
        return existing

    create_called = False

    async def _create_should_not_run(self: Any, entity: Any) -> Any:
        nonlocal create_called
        create_called = True
        return entity

    monkeypatch.setattr(FeatureQASessionRepository, "get_by_thread", _has_existing)
    monkeypatch.setattr(FeatureQASessionRepository, "create", _create_should_not_run)

    await _seed_qa_session_for_match(
        MagicMock(),
        MagicMock(id=uuid.uuid4()),
        triage,
        "bud",
        bud,
        query_text="anything",
    )

    assert create_called is False, "must not insert a second Q&A session on the same thread"
