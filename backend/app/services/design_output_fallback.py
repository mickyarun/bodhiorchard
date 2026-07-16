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

"""Recover a wireframe the designer answered with instead of tool-calling.

The designer skill persists through ``write_bud_design`` and replies with a
short JSON summary — the DB is the source of truth, never the reply. A model
that writes the wireframe inline and never calls the tool leaves ``job_design``
with a successful run, an empty design row, and "Agent did not call
write_bud_design MCP". The HTML it authored is thrown away. Frontier models
follow the tool contract; smaller local models (Ollama) routinely do not.

So treat the tool call as the fast path, not the only path: pull the document
out of the output and store it through the very same handler the tool would
have invoked, so sanitisation, READY marking and the ``design_updated``
timeline event stay byte-identical to a normal write.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

import structlog

from app.database import AsyncSessionLocal
from app.mcp.auth import MCPAuthResult
from app.mcp.handlers_bud_design import handle_write_bud_design
from app.repositories.organization import OrganizationRepository

logger = structlog.get_logger(__name__)

_HTML_FENCE = re.compile(r"```html\s*\n(.*?)\n\s*```", re.DOTALL | re.IGNORECASE)
_HTML_OPEN = re.compile(r"<html[\s>]", re.IGNORECASE)
_DOCTYPE = re.compile(r"<!DOCTYPE\s+html[^>]*>", re.IGNORECASE)
_DOC_END = re.compile(r"</html\s*>", re.IGNORECASE)


def _as_complete_document(text: str) -> str | None:
    """Return the single complete HTML document in ``text``, or ``None``.

    ``<html>`` is what's counted — a document carries at most one, while
    ``<!DOCTYPE html>`` is optional and only widens the start. Anything short
    of one opening plus a closing tag is rejected rather than guessed at:

    * **No closing tag** — a truncated document, or (much worse) prose that
      merely mentions ``<html>``, such as a refusal. Storing either would set
      the row READY and hand the user a refusal as a finished design.
    * **More than one** — a before/after pair, where picking either is a coin
      flip.

    The *last* closing tag wins, so a ``</html>`` inside a script string can't
    truncate the document early.
    """
    opens = list(_HTML_OPEN.finditer(text))
    if len(opens) != 1:
        return None
    ends = list(_DOC_END.finditer(text, opens[0].start()))
    if not ends:
        return None
    start = opens[0].start()
    # Reclaim a DOCTYPE only when it directly precedes the tag; one quoted
    # further up in prose is not this document's prologue.
    for doctype in _DOCTYPE.finditer(text[:start]):
        if not text[doctype.end() : start].strip():
            start = doctype.start()
    return text[start : ends[-1].end()].strip()


def extract_wireframe_html(output: str) -> str | None:
    """Return the wireframe document carried in ``output``, or ``None``.

    Accepts a lone ```html fence or a bare document, and only when the content
    is a complete document either way — a model explaining a snippet inside an
    html fence is common, and an explanatory fragment stored as the wireframe
    would be worse than reporting the miss, because nothing downstream
    re-checks the shape.
    """
    fences = list(_HTML_FENCE.finditer(output))
    if len(fences) == 1:
        fenced = _as_complete_document(fences[0].group(1))
        if fenced is not None:
            return fenced
    return _as_complete_document(output)


async def save_wireframe_from_output(
    output: str,
    *,
    org_id: uuid.UUID,
    bud_id: str,
    design_id: str,
    repo_id: str | None,
) -> bool:
    """Persist the wireframe found in ``output``; ``True`` when a row was written.

    Routes through ``handle_write_bud_design`` on the ``design_id`` path, which
    verifies the row belongs to this BUD and org before mutating, and commits
    internally. ``user=None`` is the documented agent-write shape: the timeline
    event records a NULL actor and simply earns no design-contribution credit.
    """
    html = extract_wireframe_html(output)
    if not html:
        return False

    params: dict[str, Any] = {"bud_id": bud_id, "design_id": design_id, "html": html}
    if repo_id:
        params["repo_id"] = repo_id

    try:
        async with AsyncSessionLocal() as db:
            org = await OrganizationRepository(db).get_by_id(org_id)
            if org is None:
                logger.warning("design_output_fallback_no_org", org_id=str(org_id))
                return False
            result = await handle_write_bud_design(db, MCPAuthResult(org=org, user=None), params)
    except Exception:
        # This is a recovery path for a run that already missed its tool call.
        # If the recovery itself breaks, the caller must still reach its own
        # "design failed" handling rather than the whole job dying here.
        logger.exception("design_output_fallback_failed", design_id=design_id)
        return False

    if not result.get("success"):
        logger.warning(
            "design_output_fallback_rejected",
            design_id=design_id,
            error=str(result.get("error"))[:200],
        )
        return False
    logger.info("design_output_fallback_saved", design_id=design_id, html_len=len(html))
    return True
