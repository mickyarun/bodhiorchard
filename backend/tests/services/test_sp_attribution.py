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

"""Tests for the SP-attribution judge (todo substance + review validity).

Pins the skip-LLM-when-nothing-to-weigh guarantee, the defensive JSON
parse (fences + leading narration), clamping, partial-answer fallback,
and the deterministic fallback on LLM failure.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services.sp_attribution import (
    TodoForJudgment,
    judge_sp_attribution,
    parse_sp_attribution,
)


def _todo(
    assignee: uuid.UUID, todo_id: str = "t1", title: str = "Build feature"
) -> TodoForJudgment:
    return TodoForJudgment(todo_id=todo_id, assignee_id=assignee, title=title, description="desc")


def test_parse_clean_json() -> None:
    a = uuid.uuid4()
    todos = [_todo(a, "t1"), _todo(a, "t2")]
    out = '{"todo_weights": {"t1": 0.9, "t2": 0.1}, "review_validity": {"dev": true}}'
    res = parse_sp_attribution(out, todos, ["dev"])
    assert res.todo_weights == {"t1": 0.9, "t2": 0.1}
    assert res.review_validity == {"dev": True}


def test_parse_strips_fences_and_leading_noise() -> None:
    todos = [_todo(uuid.uuid4(), "t1")]
    body = '{"todo_weights": {"t1": 0.5}, "review_validity": {}}'
    out = f"★ Insight\nHere you go:\n```json\n{body}\n```"
    res = parse_sp_attribution(out, todos, [])
    assert res.todo_weights["t1"] == 0.5


def test_parse_clamps_and_ignores_unknown() -> None:
    todos = [_todo(uuid.uuid4(), "t1")]
    out = '{"todo_weights": {"t1": 5.0, "ghost": 0.3}, "review_validity": {}}'
    res = parse_sp_attribution(out, todos, [])
    assert res.todo_weights == {"t1": 1.0}  # clamped, ghost ignored


def test_parse_partial_answer_keeps_neutral_default() -> None:
    todos = [_todo(uuid.uuid4(), "t1"), _todo(uuid.uuid4(), "t2")]
    out = '{"todo_weights": {"t1": 0.2}, "review_validity": {}}'
    res = parse_sp_attribution(out, todos, [])
    assert res.todo_weights["t1"] == 0.2
    assert res.todo_weights["t2"] == 1.0  # omitted → neutral default


def test_parse_malformed_falls_back() -> None:
    todos = [_todo(uuid.uuid4(), "t1")]
    res = parse_sp_attribution("not json at all", todos, ["dev"])
    assert res.todo_weights == {"t1": 1.0}
    assert res.review_validity == {"dev": True}


@pytest.mark.asyncio
async def test_single_assignee_skips_llm() -> None:
    a = uuid.uuid4()
    todos = [_todo(a, "t1"), _todo(a, "t2")]  # same assignee → no judgment needed
    with patch("app.services.sp_attribution.run_claude_code") as mock_run:
        res = await judge_sp_attribution(todos, ["solo_reviewer"])
    mock_run.assert_not_called()
    assert res.todo_weights == {"t1": 1.0, "t2": 1.0}
    assert res.review_validity == {"solo_reviewer": True}


@pytest.mark.asyncio
async def test_multiple_assignees_invoke_llm() -> None:
    todos = [_todo(uuid.uuid4(), "t1"), _todo(uuid.uuid4(), "t2")]
    fake = SimpleNamespace(
        success=True,
        output='{"todo_weights": {"t1": 0.8, "t2": 0.0}, "review_validity": {}}',
    )
    with patch(
        "app.services.sp_attribution.run_claude_code", new=AsyncMock(return_value=fake)
    ) as mock_run:
        res = await judge_sp_attribution(todos, [])
    mock_run.assert_awaited_once()
    assert res.todo_weights == {"t1": 0.8, "t2": 0.0}


@pytest.mark.asyncio
async def test_llm_failure_falls_back() -> None:
    todos = [_todo(uuid.uuid4(), "t1"), _todo(uuid.uuid4(), "t2")]
    fake = SimpleNamespace(success=False, output="")
    with patch("app.services.sp_attribution.run_claude_code", new=AsyncMock(return_value=fake)):
        res = await judge_sp_attribution(todos, [])
    assert res.todo_weights == {"t1": 1.0, "t2": 1.0}
