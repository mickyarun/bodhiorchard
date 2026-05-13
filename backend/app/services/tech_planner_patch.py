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

"""Diff-aware Implementation TODO touch-up on spec edit.

When a developer edits ``BUDDocument.tech_spec_md`` (chat or PATCH), the
TODO section may become stale relative to other sections (e.g. a new
Files-to-Modify row was added but the numbered TODO list was not
updated). This module decides whether an LLM round-trip is needed and,
if so, asks the ``tech-planner`` skill — in patch mode — for a fresh
``## Implementation TODO`` block, then splices it back.

The deterministic parser in :mod:`todo_parser` runs over the result —
this module never produces BUDTodo rows directly. The Claude wiring
lives in :mod:`_tech_planner_patch_llm`.
"""

import re
import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bud import BUDDocument, BUDStatus
from app.services._tech_planner_patch_llm import request_patched_section
from app.services.event_bus import publish
from app.services.todo_sync import sync_todos_for_bud

logger = structlog.get_logger(__name__)

# Captures everything from the ``## Implementation TODO`` header up to
# (but not including) the next ATX header at any level. The header line
# requires whitespace-only trailing content (``\s*\n``) to match the
# parser's stricter regex in ``_todo_parser_section.TODO_SECTION_RE`` —
# divergence here is the splice-but-don't-parse footgun where a header
# like ``## Implementation TODOs`` (extra 's') would be rewritten by
# this module but ignored by the parser, deleting every pending row.
_TODO_SECTION_RE = re.compile(
    r"(^|\n)#{1,6}\s+implementation\s+todo\s*\n(.*?)(?=\n#{1,6}\s|\Z)",
    re.IGNORECASE | re.DOTALL,
)


async def apply_tech_spec_edit(
    *,
    bud: BUDDocument,
    old_spec: str | None,
    new_spec: str,
    db: AsyncSession,
    org_id: uuid.UUID,
) -> str:
    """Patch the spec's TODO section if needed and re-sync BUDTodo rows.

    Called from the chat-driven spec update and the BUD PATCH handler
    after a developer edits ``tech_spec_md``. No-op when the BUD is not
    yet in DEVELOPMENT — TODO rows don't exist until the dev-phase
    transition crystallizes them.

    Returns the (possibly LLM-updated) spec text. When the BUD is
    pre-DEVELOPMENT, returns ``new_spec`` unchanged.
    """
    if bud.status != BUDStatus.DEVELOPMENT.value:
        return new_spec

    updated_spec = await maybe_patch_todo_section(
        bud=bud,
        old_spec=old_spec,
        new_spec=new_spec,
        db=db,
        org_id=org_id,
    )
    # Reflect the (possibly patched) spec onto the in-memory model so the
    # subsequent parser run sees the latest text and the caller's commit
    # persists the rewrite without a redundant second write.
    bud.tech_spec_md = updated_spec

    count = await sync_todos_for_bud(db, org_id, bud, mode="regenerate")
    publish(
        f"todo:{bud.id}",
        {
            "event": "todos_regenerated",
            "bud_id": str(bud.id),
            "todo_count": count,
        },
    )
    return updated_spec


async def maybe_patch_todo_section(
    *,
    bud: BUDDocument,
    old_spec: str | None,
    new_spec: str,
    db: AsyncSession,
    org_id: uuid.UUID,
) -> str:
    """Return ``new_spec``, possibly with its TODO section LLM-refreshed.

    Fast path: when the diff is entirely inside the existing TODO
    section (developer edited the list directly) or the spec is empty,
    return ``new_spec`` unchanged.

    Slow path: when the spec body changed elsewhere, call
    ``tech-planner`` in patch mode, splice the returned section in, and
    return the updated spec. On LLM failure or malformed output, return
    ``new_spec`` unchanged so the caller can still run the parser.
    """
    if not new_spec or not _body_changed_outside_todo_section(old_spec, new_spec):
        return new_spec

    patched_section = await _request_patched_section(
        bud=bud,
        old_spec=old_spec or "",
        new_spec=new_spec,
        db=db,
        org_id=org_id,
    )
    if patched_section is None:
        return new_spec
    return _splice_todo_section(new_spec, patched_section)


# Re-exported under a private name so existing tests + helpers don't see
# the module split — keeps the public API stable.
_request_patched_section = request_patched_section


def _body_changed_outside_todo_section(old: str | None, new: str) -> bool:
    """True when stripping the TODO section reveals a non-trivial diff."""
    if old is None:
        return True
    return _strip_todo_section(old).strip() != _strip_todo_section(new).strip()


def _strip_todo_section(spec: str) -> str:
    """Remove the ``## Implementation TODO`` section for diff comparison."""
    return _TODO_SECTION_RE.sub("\n", spec)


def _splice_todo_section(spec: str, replacement_section: str) -> str:
    """Insert ``replacement_section`` in place of the existing one.

    The replacement is expected to start with ``## Implementation TODO``
    (the LLM emits the full section including the header). When the spec
    has no existing section, the replacement is appended at the end.
    """
    section = replacement_section.strip()
    # Only check the first non-empty line for the header — the LLM may
    # mention the header text inside a bullet/comment lower down, and we
    # don't want that to fool the prefix-injection guard.
    first_line = next((line for line in section.splitlines() if line.strip()), "")
    if not first_line.lower().lstrip("#").strip().startswith("implementation todo"):
        section = "## Implementation TODO\n\n" + section

    if _TODO_SECTION_RE.search(spec):
        return _TODO_SECTION_RE.sub("\n" + section + "\n", spec, count=1)
    return spec.rstrip() + "\n\n" + section + "\n"
