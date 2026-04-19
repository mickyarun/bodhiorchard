# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Unit tests for the Implementation TODO parser.

Pure-function tests — no database, no HTTP.
Covers standard tech-planner output plus common edge cases.
"""

from app.services.todo_parser import parse_implementation_todos


class TestBasicParsing:
    def test_none_input(self) -> None:
        assert parse_implementation_todos(None) == []

    def test_empty_string(self) -> None:
        assert parse_implementation_todos("") == []

    def test_no_todo_section(self) -> None:
        spec = "## Executive Summary\nNo todos here."
        assert parse_implementation_todos(spec) == []

    def test_empty_todo_section(self) -> None:
        spec = "## Implementation TODO\n\n## Next Section\n"
        assert parse_implementation_todos(spec) == []


class TestNumberedItems:
    def test_standard_tech_planner_format(self) -> None:
        spec = """
## Implementation TODO

1. Create migration xxx
2. Add model column
3. Add API endpoints
   - ⟐ Code Review: backend phase
4. Create Vue component
5. Add route

## Code Review Standards
"""
        todos = parse_implementation_todos(spec)
        titles = [t.title for t in todos]
        assert "Create migration xxx" in titles
        assert "Add model column" in titles
        assert any("Code Review" in t.title for t in todos)
        # Expect 5 main items + 1 hoisted checkpoint
        assert len(todos) == 6

    def test_checkpoint_detected(self) -> None:
        spec = """## Implementation TODO
1. Do thing
2. ⟐ Code Review
3. Do other thing
"""
        todos = parse_implementation_todos(spec)
        assert todos[0].is_checkpoint is False
        assert todos[1].is_checkpoint is True
        assert todos[2].is_checkpoint is False

    def test_sequence_is_1_indexed_and_contiguous(self) -> None:
        spec = """## Implementation TODO
1. A
2. B
3. C
"""
        todos = parse_implementation_todos(spec)
        assert [t.sequence for t in todos] == [1, 2, 3]


class TestBulletedItems:
    def test_checkbox_format(self) -> None:
        spec = """## Implementation TODO
- [ ] Task A
- [ ] Task B
- [ ] Code Review gate
- [ ] Task C
"""
        todos = parse_implementation_todos(spec)
        assert len(todos) == 4
        assert [t.title for t in todos] == [
            "Task A",
            "Task B",
            "Code Review gate",
            "Task C",
        ]
        assert todos[2].is_checkpoint is True

    def test_plain_bullets(self) -> None:
        spec = """## Implementation TODO
- First task
- Second task
"""
        todos = parse_implementation_todos(spec)
        assert [t.title for t in todos] == ["First task", "Second task"]


class TestContextExtraction:
    def test_sub_bullets_become_context(self) -> None:
        spec = """## Implementation TODO
1. Create migration
   - table: user_preferences
   - FK to users, default values
2. Next task
"""
        todos = parse_implementation_todos(spec)
        assert todos[0].context_md is not None
        assert "user_preferences" in todos[0].context_md
        assert "FK to users" in todos[0].context_md
        assert todos[1].context_md is None

    def test_checkpoint_sub_bullet_hoisted_not_in_context(self) -> None:
        spec = """## Implementation TODO
1. Implement feature
   - Add tests
   - ⟐ Code Review: verify coverage
2. Next
"""
        todos = parse_implementation_todos(spec)
        # First TODO keeps "Add tests" as context
        assert todos[0].context_md is not None
        assert "Add tests" in todos[0].context_md
        assert "Code Review" not in todos[0].context_md
        # Checkpoint hoisted as its own TODO
        assert any(t.is_checkpoint and "Code Review" in t.title for t in todos)


class TestSectionDetection:
    def test_alternative_section_headers(self) -> None:
        for header in (
            "## Implementation TODO",
            "## Implementation Plan",
            "## Implementation Steps",
            "## TODO",
            "## Tasks",
            "### Implementation TODO",
        ):
            spec = f"{header}\n1. Item one\n"
            todos = parse_implementation_todos(spec)
            assert len(todos) == 1, f"failed for header: {header}"

    def test_section_ends_at_next_header(self) -> None:
        spec = """## Implementation TODO
1. First
2. Second

## Code Review Standards
1. Not a task
"""
        todos = parse_implementation_todos(spec)
        assert len(todos) == 2


class TestSafetyLimits:
    def test_title_truncated_for_oversized_input(self) -> None:
        long_title = "x" * 1000
        spec = f"## Implementation TODO\n1. {long_title}\n"
        todos = parse_implementation_todos(spec)
        assert len(todos[0].title) <= 500

    def test_context_truncated_for_oversized_input(self) -> None:
        long_context = "   " + ("y" * 5000)
        spec = f"## Implementation TODO\n1. Task\n{long_context}\n"
        todos = parse_implementation_todos(spec)
        assert todos[0].context_md is not None
        assert len(todos[0].context_md) <= 4000
