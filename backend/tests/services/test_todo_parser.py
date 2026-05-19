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

"""Tests for ``app.services.todo_parser``.

Parser is a pure function over markdown; tests assert the shape of the
returned ``ParsedTodo`` list given various realistic spec fragments.
"""

from app.services.todo_parser import ParsedTodo, parse_implementation_todos


def _section(*lines: str) -> str:
    """Wrap TODO lines in a minimal spec scaffold for parsing."""
    return "# Spec\n\n## Implementation TODO\n\n" + "\n".join(lines) + "\n"


def test_empty_input_returns_empty_list() -> None:
    assert parse_implementation_todos(None) == []
    assert parse_implementation_todos("") == []


def test_missing_section_returns_empty_list() -> None:
    spec = "# Spec\n\n## Files to Modify\n\n| a | b |\n"
    assert parse_implementation_todos(spec) == []


def test_simple_numbered_list_parses() -> None:
    spec = _section("1. First task", "2. Second task")
    todos = parse_implementation_todos(spec)
    assert [t.sequence for t in todos] == [1, 2]
    assert [t.title for t in todos] == ["First task", "Second task"]
    assert all(not t.is_checkpoint for t in todos)
    assert all(t.phase == "development" for t in todos)


def test_em_dash_suffix_populates_repo_and_files() -> None:
    spec = _section(
        "1. Add column — repo: api-service — files: a.py, b.py",
    )
    todos = parse_implementation_todos(spec, known_repo_names=["api-service"])
    assert len(todos) == 1
    assert todos[0].title == "Add column"
    assert todos[0].repo_name == "api-service"
    assert todos[0].code_locations == ["a.py", "b.py"]


def test_unknown_repo_resolves_to_none() -> None:
    spec = _section("1. Add column — repo: typo-repo — files: a.py")
    todos = parse_implementation_todos(spec, known_repo_names=["api-service"])
    assert todos[0].repo_name is None
    assert todos[0].code_locations == ["a.py"]


def test_no_metadata_suffix_yields_cross_cutting_todo() -> None:
    spec = _section("1. Cross-cutting docs update")
    todos = parse_implementation_todos(spec, known_repo_names=["api-service"])
    assert todos[0].repo_name is None
    assert todos[0].code_locations == []


def test_sub_bullets_become_context_md() -> None:
    spec = _section(
        "1. Add column — repo: api-service",
        "   - Nullable JSONB",
        "   - Initialised on first PATCH",
    )
    todos = parse_implementation_todos(spec, known_repo_names=["api-service"])
    assert todos[0].context_md is not None
    assert "Nullable JSONB" in todos[0].context_md
    assert "Initialised on first PATCH" in todos[0].context_md


def test_code_review_subbullet_hoisted_to_own_checkpoint_todo() -> None:
    spec = _section(
        "1. Add column — repo: api-service",
        "   - Some context",
        "   - ⟐ Code Review: schema phase",
        "2. Add endpoint — repo: api-service",
    )
    todos = parse_implementation_todos(spec, known_repo_names=["api-service"])
    titles = [t.title for t in todos]
    flags = [t.is_checkpoint for t in todos]
    assert titles == ["Add column", "⟐ Code Review: schema phase", "Add endpoint"]
    assert flags == [False, True, False]


def test_top_level_code_review_todo_is_a_real_work_item() -> None:
    """A top-level "Code review" TODO is a regular claimable item.

    Pins the rule introduced when code-review became a real TODO instead
    of a checkpoint marker: a TODO whose title contains "code review"
    without a ⟐/◆/◇ glyph is a normal work item — assignable, claimable
    via ``takeover_todo``, and counted in the dev → code_review gate.
    Only sub-bullets prefixed with a glyph remain as visual checkpoints.
    """
    spec = _section(
        "1. Add endpoint — repo: api-service",
        "2. Code review — repo: api-service",
    )
    todos = parse_implementation_todos(spec, known_repo_names=["api-service"])
    assert [t.title for t in todos] == ["Add endpoint", "Code review"]
    assert [t.is_checkpoint for t in todos] == [False, False]


def test_checkpoint_dropped_from_parent_context_md() -> None:
    spec = _section(
        "1. Add column — repo: api-service",
        "   - Some context",
        "   - ⟐ Code Review: schema phase",
    )
    todos = parse_implementation_todos(spec, known_repo_names=["api-service"])
    parent = todos[0]
    assert parent.context_md is not None
    assert "Code Review" not in parent.context_md


def test_max_ten_files_then_truncated() -> None:
    files = ", ".join(f"f{i}.py" for i in range(15))
    spec = _section(f"1. Bulk change — repo: api-service — files: {files}")
    todos = parse_implementation_todos(spec, known_repo_names=["api-service"])
    assert len(todos[0].code_locations) == 10
    assert todos[0].code_locations[0] == "f0.py"
    assert todos[0].code_locations[-1] == "f9.py"


def test_duplicate_files_deduplicated() -> None:
    spec = _section("1. Edit — repo: api-service — files: a.py, a.py, b.py")
    todos = parse_implementation_todos(spec, known_repo_names=["api-service"])
    assert todos[0].code_locations == ["a.py", "b.py"]


def test_backticked_paths_stripped() -> None:
    spec = _section("1. Edit — repo: api-service — files: `a.py`, `b.py`")
    todos = parse_implementation_todos(spec, known_repo_names=["api-service"])
    assert todos[0].code_locations == ["a.py", "b.py"]


def test_section_ends_at_next_header() -> None:
    spec = (
        "# Spec\n\n## Implementation TODO\n\n"
        "1. First — repo: api-service\n\n"
        "## Code Review Standards\n\n- [ ] foo\n"
    )
    todos = parse_implementation_todos(spec, known_repo_names=["api-service"])
    assert len(todos) == 1
    assert todos[0].title == "First"


def test_sequence_is_monotonic_across_hoisted_checkpoints() -> None:
    spec = _section(
        "1. A — repo: api-service",
        "   - ⟐ Code Review: phase 1",
        "2. B — repo: api-service",
        "   - ⟐ Code Review: phase 2",
        "3. C — repo: api-service",
    )
    todos = parse_implementation_todos(spec, known_repo_names=["api-service"])
    assert [t.sequence for t in todos] == [1, 2, 3, 4, 5]


def test_returns_list_of_parsed_todos() -> None:
    spec = _section("1. X — repo: api-service")
    todos = parse_implementation_todos(spec, known_repo_names=["api-service"])
    assert all(isinstance(t, ParsedTodo) for t in todos)
