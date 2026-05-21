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

"""MCP write-side handlers for BUD documents (BYO-AI surface).

Three tools wired here, all auth-aware (signature ``(db, auth, params)``):

* ``create_bud`` — creates a new BUD owned by the token's user.
* ``update_bud`` — content edit to a single BUD the token's user is the
  assignee of, restricted to the field owned by the BUD's current phase.
* ``get_bud_by_id`` — full-content fetch by UUID, scoped to the token's
  org. No assignee restriction on reads.

The write guards here are intentionally stricter than the REST PATCH
handler because the caller surface (an external LLM driven by content it
reads from the BUD itself) is more exposed to prompt-injection. See the
plan in ``plans/session-summary-feat-external-llm-mcp-unified-pancake.md``.
"""

from __future__ import annotations

import uuid as uuid_mod
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.mcp.auth import MCPAuthResult
from app.mcp.handler_utils import require_non_empty
from app.models.bud import BUDDocument, BUDStatus
from app.models.bud_version import BUDEditSource
from app.repositories import bud_version as bud_version_repo
from app.repositories.bud import BUDRepository
from app.services.bud_edit_policy import FIELD_OWNING_STATUS
from app.services.embedding_service import embedding_service
from app.services.feature_lifecycle import create_planned_feature

# Reverse of :data:`FIELD_OWNING_STATUS`: given the current BUD status,
# which markdown column is editable. Built at import time so the handler
# stays a constant-time lookup. A status absent from this map (e.g.
# DEVELOPMENT, UAT, PROD) has no MCP-editable field — the policy is
# "wait for the phase to advance".
_STATUS_TO_OWNING_FIELD: dict[BUDStatus, str] = {
    status: field for field, status in FIELD_OWNING_STATUS.items()
}

logger = structlog.get_logger(__name__)

# Per-field truncation for ``get_bud_by_id``. Bumped from the 5000-char
# cap in ``get_bud_context`` because the caller has asked for *this*
# specific BUD — they want the full content, not a list teaser.
_BUD_BY_ID_TRUNCATE = 10_000


def _err(code: str, message: str, **extra: Any) -> dict[str, Any]:
    """Build a soft-failure result dict picked up by the remote dispatcher.

    Streamable.py inspects ``"error" in result`` and flips the MCP
    ``isError`` flag in the response envelope, so the desktop client
    routes the message through its error UI rather than treating it as
    LLM-readable content. The ``code`` lets clients branch programmatically.
    """
    return {"success": False, "error": message, "code": code, **extra}


async def handle_create_bud(
    db: AsyncSession,
    auth: MCPAuthResult,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Create a new BUD owned by the calling user.

    Refuses org-level tokens (``auth.user is None``) — creator/assignee
    attribution is load-bearing for the assignee-only update guard, so
    creating a BUD without an identifiable user would leave it stranded
    in a state nobody can edit via MCP.
    """
    if auth.user is None:
        return _err(
            "user_token_required",
            "create_bud requires a per-user MCP token; org-level tokens cannot create BUDs.",
        )

    error = require_non_empty(params, "title", "requirements_md")
    if error:
        return error

    title = params["title"]
    body = params["requirements_md"]

    bud_repo = BUDRepository(db, org_id=auth.org.id)
    next_number = await bud_repo.next_bud_number()

    bud = BUDDocument(
        org_id=auth.org.id,
        bud_number=next_number,
        title=title,
        status=BUDStatus.BUD,
        requirements_md=body,
        assignee_id=auth.user.id,
    )
    await bud_repo.create(bud)

    await bud_version_repo.insert_snapshot(
        db,
        bud=bud,
        phase=bud.status,
        source=BUDEditSource.MCP,
        edited_by=auth.user.id,
        mcp_token_id=auth.token_id,
        reason="create",
    )

    # Embedding regen happens inline so the bug-linker and semantic
    # search can match this BUD immediately. Failure is non-fatal — a
    # stale embedding never produces wrong data, only worse search.
    try:
        bud.embedding = await embedding_service.embed(f"{title} {body[:500]}")
        await db.flush()
    except Exception:
        logger.warning("mcp_create_bud_embedding_failed", bud_number=next_number, exc_info=True)

    try:
        await create_planned_feature(db, auth.org.id, next_number, title, body)
    except Exception:
        logger.warning("mcp_create_bud_feature_link_failed", exc_info=True)

    logger.info(
        "mcp_create_bud",
        org_id=str(auth.org.id),
        user_id=str(auth.user.id),
        token_id=str(auth.token_id) if auth.token_id else None,
        bud_id=str(bud.id),
        bud_number=next_number,
    )
    return {
        "success": True,
        "id": str(bud.id),
        "bud_number": next_number,
        "title": title,
    }


async def handle_update_bud(
    db: AsyncSession,
    auth: MCPAuthResult,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Update the phase-owned content field of one BUD.

    The caller never names the field directly. The server resolves it
    from the BUD's current status against :data:`FIELD_OWNING_STATUS`,
    which both (a) tracks the same policy the UI mirrors and (b)
    forecloses an entire class of injection where an attacker LLM
    prompts the agent to write ``tech_spec_md`` while the BUD is still
    in the BUD phase.

    Guard order (fail-fast):

    1. token is per-user (no org-level writes)
    2. ``bud_id`` parses + BUD exists in the token's org
    3. ``bud.assignee_id == auth.user.id``
    4. BUD is not in a terminal phase
    5. current phase has an owning content field
    6. ``content`` is non-empty after strip
    """
    if auth.user is None:
        return _err("user_token_required", "update_bud requires a per-user MCP token.")

    error = require_non_empty(params, "bud_id", "content")
    if error:
        return error

    try:
        bud_id = uuid_mod.UUID(str(params["bud_id"]))
    except ValueError:
        return _err("bad_bud_id", "bud_id must be a UUID.")

    bud_repo = BUDRepository(db, org_id=auth.org.id)
    bud = await bud_repo.get_by_id(bud_id)
    if bud is None:
        return _err("not_found", f"No BUD with id {bud_id} in this org.")

    if bud.assignee_id != auth.user.id:
        logger.info(
            "mcp_update_bud_forbidden_assignee",
            bud_id=str(bud_id),
            assignee_id=str(bud.assignee_id) if bud.assignee_id else None,
            caller_user_id=str(auth.user.id),
        )
        return _err(
            "not_assignee",
            "MCP write is restricted to BUDs you are the assignee of.",
        )

    if bud.status in (BUDStatus.CLOSED, BUDStatus.DISCARDED):
        return _err(
            "terminal_status",
            f"BUD is in '{bud.status.value}'; create a new BUD instead of editing this one.",
        )

    field = _STATUS_TO_OWNING_FIELD.get(bud.status)
    if field is None:
        return _err(
            "no_editable_field",
            f"No content field is editable in '{bud.status.value}'. "
            "Wait for the phase to advance.",
            current_status=bud.status.value,
        )

    content = str(params["content"])

    await bud_version_repo.insert_snapshot(
        db,
        bud=bud,
        phase=bud.status,
        source=BUDEditSource.MCP,
        edited_by=auth.user.id,
        mcp_token_id=auth.token_id,
    )

    setattr(bud, field, content)

    # Refresh the embedding only when requirements_md changes — every
    # other field is downstream context the search pipeline doesn't
    # index.
    if field == "requirements_md":
        try:
            bud.embedding = await embedding_service.embed(f"{bud.title} {content[:500]}")
        except Exception:
            logger.warning("mcp_update_bud_embedding_failed", bud_id=str(bud_id), exc_info=True)

    await db.flush()

    logger.info(
        "mcp_update_bud",
        org_id=str(auth.org.id),
        user_id=str(auth.user.id),
        token_id=str(auth.token_id) if auth.token_id else None,
        bud_id=str(bud_id),
        phase=bud.status.value,
        field=field,
        content_len=len(content),
    )
    return {
        "success": True,
        "id": str(bud.id),
        "bud_number": bud.bud_number,
        "field": field,
        "phase": bud.status.value,
    }


async def handle_get_bud_by_id(
    db: AsyncSession,
    auth: MCPAuthResult,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Return full content for a single BUD, org-scoped.

    No assignee restriction on reads — a developer drafting a related
    BUD should be able to pull context from their teammate's in-flight
    work.
    """
    error = require_non_empty(params, "bud_id")
    if error:
        return error

    try:
        bud_id = uuid_mod.UUID(str(params["bud_id"]))
    except ValueError:
        return _err("bad_bud_id", "bud_id must be a UUID.")

    bud_repo = BUDRepository(db, org_id=auth.org.id)
    bud = await bud_repo.get_by_id(bud_id)
    if bud is None:
        return _err("not_found", f"No BUD with id {bud_id} in this org.")

    def _truncate(value: str | None) -> str | None:
        if value is None:
            return None
        return value if len(value) <= _BUD_BY_ID_TRUNCATE else value[:_BUD_BY_ID_TRUNCATE] + "…"

    return {
        "id": str(bud.id),
        "bud_number": bud.bud_number,
        "title": bud.title,
        "status": bud.status.value,
        "assignee_id": str(bud.assignee_id) if bud.assignee_id else None,
        "requirements_md": _truncate(bud.requirements_md),
        "tech_spec_md": _truncate(bud.tech_spec_md),
        "test_plan_md": _truncate(bud.test_plan_md),
        "code_review_comments": bud.code_review_comments,
        "auto_generate_phases": bud.auto_generate_phases,
    }
