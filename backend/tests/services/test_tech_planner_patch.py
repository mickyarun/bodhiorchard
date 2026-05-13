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

"""Tests for the diff-aware Implementation TODO patch flow.

The patch flow has three behaviours under test:
1. Diff confined to the TODO section → fast path, no LLM call.
2. Diff in spec body → tech-planner ``patch_todo`` runs; section spliced.
3. LLM returns malformed output → spec returned unchanged so the parser
   can still run on the developer's text.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services import _tech_planner_patch_llm, tech_planner_patch
from app.services.tech_planner_patch import maybe_patch_todo_section


def _bud() -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4())


def _spec(body: str, todo_section: str) -> str:
    return (
        f"# Spec\n\n{body}\n\n## Implementation TODO\n\n"
        f"{todo_section}\n\n## Code Review Standards\n\n- [ ] foo\n"
    )


@pytest.mark.asyncio
async def test_diff_inside_todo_section_takes_fast_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Editing only the TODO section must not invoke the LLM."""
    old = _spec("body content", "1. Old item — repo: api-service")
    new = _spec("body content", "1. New item — repo: api-service")

    request_mock = AsyncMock()
    monkeypatch.setattr(tech_planner_patch, "_request_patched_section", request_mock)

    result = await maybe_patch_todo_section(
        bud=_bud(),
        old_spec=old,
        new_spec=new,
        db=MagicMock(),
        org_id=uuid.uuid4(),
    )

    assert result == new
    request_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_body_change_calls_llm_and_splices(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A body diff must trigger the LLM patch; result is spliced back."""
    old = _spec("body content", "1. Item one — repo: api-service")
    new = _spec("body content with a new sentence.", "1. Item one — repo: api-service")
    replacement = (
        "## Implementation TODO\n\n"
        "1. Item one — repo: api-service\n"
        "2. New item from LLM — repo: api-service\n"
    )

    monkeypatch.setattr(
        tech_planner_patch,
        "_request_patched_section",
        AsyncMock(return_value=replacement),
    )

    result = await maybe_patch_todo_section(
        bud=_bud(),
        old_spec=old,
        new_spec=new,
        db=MagicMock(),
        org_id=uuid.uuid4(),
    )

    assert "New item from LLM" in result
    # Only one Implementation TODO header survives (original replaced).
    assert result.lower().count("## implementation todo") == 1


@pytest.mark.asyncio
async def test_malformed_llm_output_returns_new_spec_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLM failure must NOT corrupt the spec; caller falls through to parser."""
    old = _spec("body", "1. Item — repo: api-service")
    new = _spec("body changed", "1. Item — repo: api-service")

    monkeypatch.setattr(
        tech_planner_patch,
        "_request_patched_section",
        AsyncMock(return_value=None),
    )

    result = await maybe_patch_todo_section(
        bud=_bud(),
        old_spec=old,
        new_spec=new,
        db=MagicMock(),
        org_id=uuid.uuid4(),
    )

    assert result == new


@pytest.mark.asyncio
async def test_no_old_spec_triggers_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    """A first-time spec (no prior version) is treated as a body change."""
    new = _spec("body", "1. Item — repo: api-service")

    request_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(tech_planner_patch, "_request_patched_section", request_mock)

    result = await maybe_patch_todo_section(
        bud=_bud(),
        old_spec=None,
        new_spec=new,
        db=MagicMock(),
        org_id=uuid.uuid4(),
    )

    assert result == new
    request_mock.assert_awaited_once()


def test_extract_section_accepts_fenced_block() -> None:
    fenced = "```markdown\n## Implementation TODO\n\n1. foo\n```"
    assert _tech_planner_patch_llm.extract_section(fenced) is not None


def test_extract_section_accepts_bare_markdown() -> None:
    bare = "## Implementation TODO\n\n1. foo"
    assert _tech_planner_patch_llm.extract_section(bare) is not None


def test_extract_section_rejects_output_missing_header() -> None:
    bogus = "Sure! Here is the section:\n\n1. foo"
    assert _tech_planner_patch_llm.extract_section(bogus) is None


def test_strip_todo_section_removes_only_the_section() -> None:
    spec = _spec("body content", "1. Item — repo: api-service")
    stripped = tech_planner_patch._strip_todo_section(spec)
    assert "body content" in stripped
    assert "Item — repo: api-service" not in stripped
    assert "Code Review Standards" in stripped


def test_splice_replaces_existing_section() -> None:
    spec = _spec("body", "1. Old — repo: api-service")
    replacement = "## Implementation TODO\n\n1. New — repo: api-service"
    out = tech_planner_patch._splice_todo_section(spec, replacement)
    assert "1. New" in out
    assert "1. Old" not in out


def test_splice_appends_when_no_existing_section() -> None:
    spec = "# Spec\n\n## Files\n\n- a.py\n"
    replacement = "## Implementation TODO\n\n1. New — repo: api-service"
    out = tech_planner_patch._splice_todo_section(spec, replacement)
    assert "1. New" in out
    assert out.count("## Implementation TODO") == 1
