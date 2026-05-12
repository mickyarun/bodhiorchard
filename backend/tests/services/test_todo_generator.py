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

"""Tests for the ``todo-generator`` agent wrapper.

Stubs ``run_claude_code`` so the suite never spawns the real Claude CLI
subprocess; exercises the JSON extraction, Pydantic validation, and
progress-event side effects of ``generate_todos_for_bud``.
"""

import json
import uuid
from types import SimpleNamespace
from typing import Any, cast

import pytest

from app.models.bud import BUDDocument
from app.services import todo_generator
from app.services.claude_runner import ClaudeRunResult
from app.services.todo_generator import (
    TodoGenerationError,
    generate_todos_for_bud,
)


def _stub_bud(tech_spec_md: str | None = "## Plan") -> BUDDocument:
    """Minimal BUDDocument shape — the generator only reads two attrs."""
    stub = SimpleNamespace(id=uuid.uuid4(), tech_spec_md=tech_spec_md)
    return cast(BUDDocument, stub)


def _good_payload(items: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    if items is None:
        items = [
            {
                "sequence": 1,
                "title": "Add a column",
                "description": "Adds a nullable column for X.",
                "repo_name": "repo-a",
                "code_locations": ["backend/app/models/x.py"],
                "context_md": "Edge cases: nulls, defaults.",
                "is_checkpoint": False,
                "phase": "development",
            },
        ]
    return {"items": items}


def _wrap_json(data: dict[str, Any]) -> str:
    return f"```json\n{json.dumps(data)}\n```"


def _published_events(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, dict[str, Any]]]:
    events: list[tuple[str, dict[str, Any]]] = []

    def _capture(topic: str, payload: dict[str, Any]) -> None:
        events.append((topic, payload))

    monkeypatch.setattr(todo_generator, "publish", _capture)
    return events


def _stub_runner(
    monkeypatch: pytest.MonkeyPatch,
    *,
    output: str = "",
    success: bool = True,
    error: str | None = None,
    invoke_callback_with: list[str] | None = None,
) -> None:
    async def _fake_run(prompt: str, **kwargs: Any) -> ClaudeRunResult:
        cb = kwargs.get("progress_callback")
        if cb is not None and invoke_callback_with:
            for tool in invoke_callback_with:
                cb(tool, {})
        return ClaudeRunResult(success=success, output=output, error=error)

    monkeypatch.setattr(todo_generator, "run_claude_code", _fake_run)


# ── happy path ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_happy_path_returns_validated_items(monkeypatch: pytest.MonkeyPatch) -> None:
    events = _published_events(monkeypatch)
    _stub_runner(monkeypatch, output=_wrap_json(_good_payload()))

    items = await generate_todos_for_bud(_stub_bud(), [(uuid.uuid4(), "repo-a")])

    assert len(items) == 1
    assert items[0].title == "Add a column"
    assert items[0].repo_name == "repo-a"
    assert items[0].code_locations == ["backend/app/models/x.py"]
    # start + complete events fire on the topic
    event_names = [payload["event"] for _, payload in events]
    assert event_names[0] == "generating_start"
    assert event_names[-1] == "generating_complete"
    assert events[-1][1]["count"] == 1


# ── failure modes ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_runner_failure_raises_and_emits_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    events = _published_events(monkeypatch)
    _stub_runner(monkeypatch, output="", success=False, error="cli not found")

    with pytest.raises(TodoGenerationError, match="cli not found"):
        await generate_todos_for_bud(_stub_bud(), [])

    assert any(p["event"] == "generating_failed" for _, p in events)


@pytest.mark.asyncio
async def test_unparseable_output_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _published_events(monkeypatch)
    _stub_runner(monkeypatch, output="not json at all")

    with pytest.raises(TodoGenerationError, match="no parseable JSON"):
        await generate_todos_for_bud(_stub_bud(), [])


@pytest.mark.asyncio
async def test_missing_title_field_fails_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    _published_events(monkeypatch)
    bad = {"items": [{"sequence": 1, "phase": "development"}]}
    _stub_runner(monkeypatch, output=_wrap_json(bad))

    with pytest.raises(TodoGenerationError, match="schema validation"):
        await generate_todos_for_bud(_stub_bud(), [])


@pytest.mark.asyncio
async def test_oversized_title_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    _published_events(monkeypatch)
    oversized = _good_payload(
        [
            {
                "sequence": 1,
                "title": "x" * 501,  # cap is 500
                "phase": "development",
            },
        ]
    )
    _stub_runner(monkeypatch, output=_wrap_json(oversized))

    with pytest.raises(TodoGenerationError, match="schema validation"):
        await generate_todos_for_bud(_stub_bud(), [])


@pytest.mark.asyncio
async def test_validation_error_publishes_generating_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pydantic validation failure must clear the UI spinner, not just raise."""
    events = _published_events(monkeypatch)
    bad = {"items": [{"sequence": 1, "phase": "development"}]}  # missing title
    _stub_runner(monkeypatch, output=_wrap_json(bad))

    with pytest.raises(TodoGenerationError):
        await generate_todos_for_bud(_stub_bud(), [])

    assert any(p["event"] == "generating_failed" for _, p in events)


@pytest.mark.asyncio
async def test_progress_callback_forwards_tool_use_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The agent's tool_use callbacks must reach the WS topic."""
    events = _published_events(monkeypatch)
    _stub_runner(
        monkeypatch,
        output=_wrap_json(_good_payload()),
        invoke_callback_with=["Read", "Grep"],
    )

    await generate_todos_for_bud(_stub_bud(), [])

    tool_events = [p for _, p in events if p["event"] == "generating_tool_use"]
    assert [e["tool"] for e in tool_events] == ["Read", "Grep"]


@pytest.mark.asyncio
async def test_too_many_code_locations_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    _published_events(monkeypatch)
    oversized = _good_payload(
        [
            {
                "sequence": 1,
                "title": "ok",
                "code_locations": [f"f{i}.py" for i in range(11)],  # cap is 10
                "phase": "development",
            },
        ]
    )
    _stub_runner(monkeypatch, output=_wrap_json(oversized))

    with pytest.raises(TodoGenerationError, match="schema validation"):
        await generate_todos_for_bud(_stub_bud(), [])
