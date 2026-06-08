# Copyright 2025-2026 Arun Rajkumar
#
# Licensed under the Apache License, Version 2.0 (the "License").

"""Scope-rule contract for the triage duplicate verifier prompt.

The verifier is the last line of defence against wrong-variant "already
tracked" replies (image-3 in the bug report — a request about banks in
country A getting matched to a BUD that names banks in country B). Two
guardrails live in the prompt body:

1. The original generic-topic-word rule ("user", "data", "dashboard"…) —
   it stops topic overlap from passing as a real match.
2. The named-entity scope rule — it stops *specific-thing* mismatch
   (different vendor, geography, product, integration target…) from
   being treated as the same feature.

This test pins both as snapshot substrings. It does NOT assert exact
wording — the prompt is allowed to evolve — only that the categories
the verifier reasons about are still surfaced to the LLM.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.services import slack_intake
from app.services.slack_intake import _verify_duplicate_with_llm


def _fake_bud_candidate() -> tuple[str, Any, float]:
    """A BUD-shaped candidate the verifier formats into one prompt line."""
    bud = MagicMock(
        bud_number=21,
        title="Add Bank A, Bank B & Bank C support",
        requirements_md="Integrate three high-street banks in market X.",
        status=MagicMock(value="in_progress"),
        id=uuid.uuid4(),
    )
    return ("bud", bud, 0.72)


@pytest.mark.asyncio
async def test_verifier_prompt_contains_topic_and_entity_scope_rules(
    monkeypatch: Any,
) -> None:
    """The verifier must brief the LLM on BOTH generic-topic-word and
    named-entity scope rules. Skipping either lets the wrong class of
    mismatch slip through silently."""
    captured: dict[str, str] = {}

    async def _capture_run(*, prompt: str, **kwargs: Any) -> Any:
        captured["prompt"] = prompt
        return MagicMock(success=False, error="captured-only", output="")

    monkeypatch.setattr(slack_intake, "run_claude_code", _capture_run)

    await _verify_duplicate_with_llm(
        query_text="Integrate Bank D in market Y",
        candidates=[_fake_bud_candidate()],
    )

    prompt = captured["prompt"]

    # Pre-existing rule — keep it pinned so a future edit can't drop it
    # while adding the new one.
    assert "generic topic words" in prompt
    assert '"dashboard"' in prompt

    # New named-entity rule. Pin the section header and a small core of
    # category words rather than every synonym — that way a future copy
    # edit can swap "organisations" ↔ "organizations" or drop one term
    # for another without breaking the contract this test is meant to
    # protect. The point is that *some* named-entity vocabulary is
    # reaching the LLM, not the exact wording.
    assert "Named-entity scope" in prompt
    for token in ("vendors", "geographies", "integration targets"):
        assert token in prompt, f"missing named-entity category: {token}"

    # The whole point: when the entity differs, the verifier must vote
    # no_match — not match-with-a-warning.
    assert "no_match" in prompt
