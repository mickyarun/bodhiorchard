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

"""Tests for ``iteration_max_turns`` parsing and the design-iteration formula.

The field replaces the previous hard-coded ``DESIGN_ITERATION_MAX_TURNS = 4``
in ``job_chat.py`` — admins now set the iteration cap per skill. These tests
lock the fallback semantics so a future refactor can't silently reintroduce
a constant override.
"""

from pathlib import Path

import pytest

from app.services.skill_loader import Skill, _parse_frontmatter, load_skill


def _make_skill(*, max_turns: int = 0, iteration_max_turns: int = 0) -> Skill:
    return Skill(
        name="test",
        slug="test",
        description="",
        tools=[],
        mcp_tools=[],
        prompt="",
        max_turns=max_turns,
        iteration_max_turns=iteration_max_turns,
    )


def _iteration_turns(skill: Skill | None, *, is_design_iteration: bool) -> int:
    """Mirror of the formula in ``job_chat.py`` so the test locks the contract.

    Kept in lockstep with the production line in ``job_chat.py``: when
    that line changes, this test must move with it.
    """
    skill_turns = skill.max_turns if skill else 0
    skill_iteration_turns = skill.iteration_max_turns_or_base() if skill else 0
    return skill_iteration_turns if is_design_iteration else skill_turns


def test_iteration_turns_uses_iteration_max_turns_when_set() -> None:
    skill = _make_skill(max_turns=12, iteration_max_turns=6)
    assert _iteration_turns(skill, is_design_iteration=True) == 6


def test_iteration_turns_falls_back_to_max_turns_when_iteration_field_zero() -> None:
    """0 is the documented sentinel for 'fall back'."""
    skill = _make_skill(max_turns=12, iteration_max_turns=0)
    assert _iteration_turns(skill, is_design_iteration=True) == 12


def test_iteration_turns_ignores_iteration_field_for_non_design_sections() -> None:
    """Only the design section applies the iteration override."""
    skill = _make_skill(max_turns=10, iteration_max_turns=4)
    assert _iteration_turns(skill, is_design_iteration=False) == 10


def test_iteration_turns_zero_when_skill_missing() -> None:
    """Missing skill ⇒ 0 (claude_runner omits --max-turns when 0)."""
    assert _iteration_turns(None, is_design_iteration=True) == 0
    assert _iteration_turns(None, is_design_iteration=False) == 0


def test_frontmatter_parses_iteration_max_turns_as_int() -> None:
    content = (
        "---\n"
        "name: Tester\n"
        "description: ''\n"
        "tools: []\n"
        "mcp_tools: []\n"
        "max_turns: 12\n"
        "iteration_max_turns: 6\n"
        "---\n"
        "body text"
    )
    frontmatter, body = _parse_frontmatter(content)
    assert frontmatter["iteration_max_turns"] == 6
    assert body.strip() == "body text"


def test_frontmatter_defaults_iteration_max_turns_to_zero_when_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Skill files that don't declare the field load as 0 (the fallback sentinel)."""
    skill_file = tmp_path / "iter-turn-fallback-skill.md"
    skill_file.write_text(
        "---\nname: Tester\ndescription: ''\ntools: []\nmcp_tools: []\nmax_turns: 8\n---\nbody"
    )
    monkeypatch.setattr("app.services.skill_loader.SKILLS_DIR", tmp_path)
    skill = load_skill("iter-turn-fallback-skill")
    assert skill.max_turns == 8
    assert skill.iteration_max_turns == 0


@pytest.mark.parametrize(
    ("max_turns", "iteration_max_turns", "expected"),
    [
        (0, 0, 0),  # Both unset ⇒ 0 (no --max-turns flag)
        (0, 5, 5),  # Iteration override even when max_turns is 0
        (12, 0, 12),  # Fall back path
        (12, 4, 4),  # Both set ⇒ iteration wins
    ],
)
def test_iteration_turns_table(max_turns: int, iteration_max_turns: int, expected: int) -> None:
    skill = _make_skill(max_turns=max_turns, iteration_max_turns=iteration_max_turns)
    assert _iteration_turns(skill, is_design_iteration=True) == expected
