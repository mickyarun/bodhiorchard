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

"""Parse the Implementation TODO section from a tech spec into TODOs.

The tech-planner agent produces a numbered checklist in a section titled
``## Implementation TODO``. Each numbered item becomes one ``BUDTodo``.
Sub-bullets indented under an item become that TODO's ``context_md``.
Lines containing ``⟐`` or ``Code Review`` are flagged as checkpoints.

The parser is intentionally tolerant — tech specs vary in formatting.
If no TODO section is found, an empty list is returned (BUD falls back
to the existing single-assignee workflow).
"""

import re
from dataclasses import dataclass

_HEADER_RE = re.compile(r"^#{1,6}\s+(.*?)\s*$")
_TODO_SECTION_RE = re.compile(
    r"^#{1,6}\s+(implementation\s+(?:todo|plan|steps?)|todo|tasks?)\s*$",
    re.IGNORECASE,
)
# Matches lines starting with "1. ", "1) ", "- [ ] ", "- "
_ITEM_RE = re.compile(
    r"^(?P<indent>\s*)"
    r"(?:(?P<num>\d+)[.)]\s+|(?P<bullet>[-*+])\s+(?:\[[ xX]\]\s+)?)"
    r"(?P<text>.+?)\s*$"
)
_CHECKPOINT_RE = re.compile(r"[⟐◆◇]|\bcode\s+review\b", re.IGNORECASE)

_MAX_TITLE_LEN = 500
_MAX_CONTEXT_LEN = 4000


@dataclass
class ParsedTodo:
    """A single TODO parsed from the tech spec."""

    sequence: int
    title: str
    is_checkpoint: bool
    phase: str
    context_md: str | None = None


def parse_implementation_todos(tech_spec_md: str | None) -> list[ParsedTodo]:
    """Extract TODO items from a tech spec markdown blob.

    Returns an empty list when the spec is missing, has no TODO section,
    or the section is empty. The caller should treat empty results as
    "no structured TODOs — fall back to single-assignee workflow".
    """
    if not tech_spec_md:
        return []

    lines = tech_spec_md.splitlines()
    section_lines = _extract_todo_section(lines)
    if not section_lines:
        return []

    raw_items = _group_items(section_lines)
    if not raw_items:
        return []

    return _build_todos(raw_items)


def _extract_todo_section(lines: list[str]) -> list[str]:
    """Return lines between the Implementation TODO header and the next header."""
    start_idx: int | None = None
    for idx, line in enumerate(lines):
        if _TODO_SECTION_RE.match(line):
            start_idx = idx + 1
            break
    if start_idx is None:
        return []

    end_idx = len(lines)
    for idx in range(start_idx, len(lines)):
        if _HEADER_RE.match(lines[idx]):
            end_idx = idx
            break

    return lines[start_idx:end_idx]


def _group_items(section_lines: list[str]) -> list[tuple[str, list[str]]]:
    """Group section lines into (main_item_text, sub_lines) tuples.

    A "main item" is a numbered line at indent 0 (or a bulleted line
    at indent 0 if no numbered items exist). Indented lines following
    a main item are its context until the next main item appears.
    """
    # First pass: detect whether the section uses numbered or bulleted items.
    has_numbered = any(
        (match := _ITEM_RE.match(line)) and match.group("num") and not match.group("indent")
        for line in section_lines
    )

    groups: list[tuple[str, list[str]]] = []
    current_text: str | None = None
    current_context: list[str] = []

    for line in section_lines:
        stripped = line.rstrip()
        if not stripped:
            if current_text is not None:
                current_context.append("")
            continue

        match = _ITEM_RE.match(line)
        # Numbered items at indent 0 are always main items. Bullets at
        # indent 0 are main only if the section has no numbered items.
        is_main_item = bool(
            match and not match.group("indent") and (match.group("num") or not has_numbered)
        )

        if is_main_item:
            if current_text is not None:
                groups.append((current_text, current_context))
            assert match is not None
            current_text = match.group("text").strip()
            current_context = []
        elif current_text is not None:
            current_context.append(stripped)

    if current_text is not None:
        groups.append((current_text, current_context))

    return groups


def _build_todos(raw_items: list[tuple[str, list[str]]]) -> list[ParsedTodo]:
    """Turn raw (text, context) pairs into sequenced ParsedTodo records.

    Checkpoint sub-bullets are hoisted into their own ParsedTodo with
    ``is_checkpoint=True`` so they appear in order in the UI.
    """
    todos: list[ParsedTodo] = []
    sequence = 0

    for text, context_lines in raw_items:
        sequence += 1
        is_checkpoint = bool(_CHECKPOINT_RE.search(text))
        context_md, checkpoint_sub_items = _split_context_and_checkpoints(context_lines)

        todos.append(
            ParsedTodo(
                sequence=sequence,
                title=_truncate(text, _MAX_TITLE_LEN),
                is_checkpoint=is_checkpoint,
                phase="development",
                context_md=_truncate(context_md, _MAX_CONTEXT_LEN) if context_md else None,
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
                )
            )

    return todos


def _split_context_and_checkpoints(
    context_lines: list[str],
) -> tuple[str, list[str]]:
    """Separate checkpoint sub-bullets from regular context lines.

    Checkpoint lines become their own TODOs; everything else is joined
    into the parent TODO's context_md.
    """
    regular: list[str] = []
    checkpoints: list[str] = []

    for line in context_lines:
        if _CHECKPOINT_RE.search(line):
            text = _strip_bullet_prefix(line)
            if text:
                checkpoints.append(text)
        else:
            regular.append(line)

    # Trim leading/trailing empty lines from regular context
    while regular and not regular[0].strip():
        regular.pop(0)
    while regular and not regular[-1].strip():
        regular.pop()

    return "\n".join(regular), checkpoints


def _strip_bullet_prefix(line: str) -> str:
    """Remove bullet/checkbox/numbering prefix from a line."""
    match = _ITEM_RE.match(line)
    if match:
        return match.group("text").strip()
    return line.strip()


def _truncate(text: str, limit: int) -> str:
    """Safely truncate text to prevent oversized DB writes."""
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"
