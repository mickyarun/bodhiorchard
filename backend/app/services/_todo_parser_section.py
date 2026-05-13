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

"""Section + line grouping helpers for :mod:`todo_parser`.

Two pure functions split out so the parser's public module stays under
the project's per-file line cap. Both are package-private — callers use
:func:`app.services.todo_parser.parse_implementation_todos`.
"""

import re

_HEADER_RE = re.compile(r"^#{1,6}\s+(.*?)\s*$")
# Canonical section header — kept in sync with the tech-planner skill's
# emission contract and with ``tech_planner_patch._TODO_SECTION_RE``.
TODO_SECTION_RE = re.compile(
    r"^#{1,6}\s+implementation\s+todo\s*$",
    re.IGNORECASE,
)
# Numbered ("1. ", "1) ") or bulleted ("- [ ] ", "- ", "* ", "+ ") lines.
ITEM_RE = re.compile(
    r"^(?P<indent>\s*)"
    r"(?:(?P<num>\d+)[.)]\s+|(?P<bullet>[-*+])\s+(?:\[[ xX]\]\s+)?)"
    r"(?P<text>.+?)\s*$"
)


def extract_todo_section(lines: list[str]) -> list[str]:
    """Return lines between the Implementation TODO header and the next header."""
    start_idx: int | None = None
    for idx, line in enumerate(lines):
        if TODO_SECTION_RE.match(line):
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


def group_items(section_lines: list[str]) -> list[tuple[str, list[str]]]:
    """Group section lines into ``(main_item_text, sub_lines)`` tuples.

    A "main item" is a numbered line at indent 0 (or a bulleted line at
    indent 0 if no numbered items exist). Indented lines following a
    main item are its context until the next main item appears.
    """
    has_numbered = any(
        (match := ITEM_RE.match(line)) and match.group("num") and not match.group("indent")
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

        match = ITEM_RE.match(line)
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


def strip_bullet_prefix(line: str) -> str:
    """Remove bullet / checkbox / numbering prefix from a line."""
    match = ITEM_RE.match(line)
    if match:
        return match.group("text").strip()
    return line.strip()
