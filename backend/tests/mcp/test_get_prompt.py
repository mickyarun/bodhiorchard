# Copyright 2025-2026 Arun Rajkumar
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""Tests for the ``get_prompt`` MCP tool.

Validates the BYO-AI surface that lets a user pull our org's active
prompt for a given BUD stage. Two invariants matter most:

1. Only the documented ``task_type`` values are accepted — any other
   string returns an ``error`` payload, never a 500.
2. The handler resolves through ``resolve_skill_for_agent`` (the same
   override-aware resolver our internal agents use) so the external LLM
   gets exactly the prompt the in-process agent would have run.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.mcp.handlers_prompts import TASK_TYPE_TO_STAGE, handle_get_prompt


@pytest.mark.asyncio
async def test_unknown_task_type_returns_error_payload(monkeypatch: Any) -> None:
    """Garbage task_type must produce an MCP-friendly error, not a 500."""
    org = MagicMock(id=uuid.uuid4())
    result = await handle_get_prompt(MagicMock(), org, {"task_type": "not_a_stage"})
    assert "error" in result
    assert "task_type" in result["error"]


@pytest.mark.asyncio
async def test_missing_task_type_returns_error_payload() -> None:
    """No task_type at all is the same shape as a bad task_type."""
    org = MagicMock(id=uuid.uuid4())
    result = await handle_get_prompt(MagicMock(), org, {})
    assert "error" in result


@pytest.mark.asyncio
async def test_known_task_types_dispatch_to_resolver(monkeypatch: Any) -> None:
    """Each valid task_type calls resolve_skill_for_agent and returns the prompt."""
    captured: list[tuple[str, uuid.UUID]] = []

    async def _fake_resolve(agent_name: str, org_id: uuid.UUID, db: Any, **kw: Any) -> Any:
        captured.append((agent_name, org_id))
        return MagicMock(skill_slug=f"{agent_name}-default", prompt=f"PROMPT FOR {agent_name}")

    monkeypatch.setattr("app.agents.skill_mapping.resolve_skill_for_agent", _fake_resolve)

    org = MagicMock(id=uuid.uuid4())
    for task_type in TASK_TYPE_TO_STAGE:
        result = await handle_get_prompt(MagicMock(), org, {"task_type": task_type})
        assert "error" not in result, f"task_type={task_type!r} unexpectedly errored: {result}"
        assert result["task_type"] == task_type
        assert result["prompt"].startswith("PROMPT FOR ")
        assert result["skill_slug"].endswith("-default")

    # Resolver was called once per known task_type with this org's id.
    assert len(captured) == len(TASK_TYPE_TO_STAGE)
    assert {org_id for _, org_id in captured} == {org.id}


@pytest.mark.asyncio
async def test_no_active_skill_returns_error_payload(monkeypatch: Any) -> None:
    """If the org has no seeded skill for the agent type, surface as error."""

    async def _fake_resolve_none(*args: Any, **kw: Any) -> None:
        return None

    monkeypatch.setattr(
        "app.agents.skill_mapping.resolve_skill_for_agent", _fake_resolve_none
    )

    org = MagicMock(id=uuid.uuid4())
    result = await handle_get_prompt(MagicMock(), org, {"task_type": "bud"})
    assert "error" in result
    assert "skill" in result["error"].lower()
