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

"""Parse the Implementation TODO section from a tech spec into BUDTodo rows.

The ``tech-planner`` skill emits a numbered checklist under
``## Implementation TODO``. Each line follows the convention::

    1. <title> — repo: <repo_name> — files: <path1>, <path2>
       - sub-bullet becomes context_md
       - ⟐ Code Review: <phase>   <- hoisted into its own checkpoint TODO

The em-dash suffix is parsed off the title to populate ``repo_name`` and
``code_locations``; it is optional, so a line that omits ``repo:`` /
``files:`` still yields a valid TODO (cross-cutting / unscoped).

This module is pure: no DB, no LLM, no I/O. It is the only producer of
``ParsedTodo`` records consumed by ``todo_sync._reconcile``. Section
extraction + line grouping live in :mod:`_todo_parser_section`; em-dash
suffix parsing lives in :mod:`_todo_parser_metadata`.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass, field

from app.services._todo_parser_metadata import split_metadata_suffix
from app.services._todo_parser_section import (
    extract_todo_section,
    group_items,
    strip_bullet_prefix,
)

# Checkpoints are inline visual markers the tech-arch agent emits in the
# implementation TODO section (using ⟐ / ◆ / ◇ glyphs) to delineate sub-
# phases — e.g. "design review" before moving on. They are NOT work items:
# they cannot be claimed (see ``handle_takeover_todo``) and don't show
# up in the per-developer assignment / remaining-work counts.
#
# Code review is intentionally NOT in this regex any more. It is a real
# TODO that a developer (or Claude via MCP) claims, executes, and
# completes via the standard takeover/complete flow — and it counts
# toward the dev → code_review transition gate just like any other TODO.
_CHECKPOINT_RE = re.compile(r"[⟐◆◇]", re.IGNORECASE)

_MAX_TITLE_LEN = 500
_MAX_CONTEXT_LEN = 4000


@dataclass
class ParsedTodo:
    """A single TODO parsed from the tech spec.

    Maps 1:1 onto the agent-derived columns of ``BUDTodo`` so
    ``todo_sync._reconcile`` can use the same shape it used for the old
    LLM-generated payload.
    """

    sequence: int
    title: str
    is_checkpoint: bool
    phase: str
    context_md: str | None = None
    description: str | None = None
    repo_name: str | None = None
    code_locations: list[str] = field(default_factory=list)


def parse_implementation_todos(
    tech_spec_md: str | None,
    *,
    known_repo_names: Iterable[str] = (),
) -> list[ParsedTodo]:
    """Extract TODO items from a tech spec markdown blob.

    Args:
        tech_spec_md: The full tech spec markdown. ``None`` / empty
            returns an empty list.
        known_repo_names: Repo names from ``bud.impacted_repos``. Used to
            validate the ``repo:`` suffix on each TODO line — unknown
            names are dropped (treated as cross-cutting).

    Returns:
        Sequenced, deduplicated list of ``ParsedTodo`` records. Empty
        list when no Implementation TODO section is found — caller treats
        that as "fall back to single-assignee workflow".
    """
    if not tech_spec_md:
        return []

    lines = tech_spec_md.splitlines()
    section_lines = extract_todo_section(lines)
    if not section_lines:
        return []

    raw_items = group_items(section_lines)
    if not raw_items:
        return []

    known = {name for name in known_repo_names if name}
    return _build_todos(raw_items, known_repos=known)


def _build_todos(
    raw_items: list[tuple[str, list[str]]],
    *,
    known_repos: set[str],
) -> list[ParsedTodo]:
    """Turn raw ``(text, context)`` pairs into sequenced ``ParsedTodo`` records.

    Checkpoint sub-bullets are hoisted into their own ParsedTodo with
    ``is_checkpoint=True`` so they appear in order in the UI.
    """
    todos: list[ParsedTodo] = []
    sequence = 0

    for text, context_lines in raw_items:
        sequence += 1
        title, repo_name, code_locations = split_metadata_suffix(text, known_repos)
        is_checkpoint = bool(_CHECKPOINT_RE.search(title))
        context_md, checkpoint_sub_items = _split_context_and_checkpoints(context_lines)

        todos.append(
            ParsedTodo(
                sequence=sequence,
                title=_truncate(title, _MAX_TITLE_LEN),
                is_checkpoint=is_checkpoint,
                phase="development",
                context_md=_truncate(context_md, _MAX_CONTEXT_LEN) if context_md else None,
                repo_name=repo_name,
                code_locations=code_locations,
            )
        )

        for sub_text in checkpoint_sub_items:
            sequence += 1
            todos.append(
                ParsedTodo(
                    sequence=sequence,
                    title=_truncate(sub_text, _MAX_TITLE_LEN),
                    is_checkpoint=True,
                    phase="development",
                    context_md=None,
                    repo_name=None,
                    code_locations=[],
                )
            )

    return todos


def _split_context_and_checkpoints(
    context_lines: list[str],
) -> tuple[str, list[str]]:
    """Separate checkpoint sub-bullets from regular context lines.

    Checkpoint lines become their own TODOs; everything else is joined
    into the parent TODO's ``context_md``.
    """
    regular: list[str] = []
    checkpoints: list[str] = []

    for line in context_lines:
        if _CHECKPOINT_RE.search(line):
            text = strip_bullet_prefix(line)
            if text:
                checkpoints.append(text)
        else:
            regular.append(line)

    while regular and not regular[0].strip():
        regular.pop(0)
    while regular and not regular[-1].strip():
        regular.pop()

    return "\n".join(regular), checkpoints


def _truncate(text: str, limit: int) -> str:
    """Safely truncate text to prevent oversized DB writes."""
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"
