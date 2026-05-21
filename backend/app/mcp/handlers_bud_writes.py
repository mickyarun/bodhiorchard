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
from app.models.bud import BUDDesignStatus, BUDDocument, BUDStatus
from app.models.bud_feature_link import BUDFeatureLinkSource
from app.models.bud_version import BUDEditSource
from app.repositories import bud_version as bud_version_repo
from app.repositories.bud import BUDDesignRepository, BUDRepository
from app.repositories.bud_feature_link import BUDFeatureLinkRepository
from app.repositories.bud_version import build_snapshot
from app.services.bud_edit_policy import FIELD_OWNING_STATUS
from app.services.embedding_service import embedding_service
from app.services.feature_lifecycle import create_planned_feature
from app.services.html_sanitizer import sanitize_design_html

# The MCP write surface is intentionally narrower than the REST PATCH
# policy: external LLMs may author the three creative phases (drafting
# the PRD, designing the UI, writing the tech spec). Testing and
# code-review writes stay UI/agent-driven — they involve evidence
# uploads, PR merge state, and stage-gating logic that a stateless LLM
# call should not steer.
_MCP_EDITABLE_PHASES: frozenset[BUDStatus] = frozenset(
    {BUDStatus.BUD, BUDStatus.DESIGN, BUDStatus.TECH_ARCH}
)

# Reverse of :data:`FIELD_OWNING_STATUS` for the markdown-column phases.
# ``DESIGN`` is excluded because its content lives in the ``bud_designs``
# table — see :func:`_apply_design_content` for the dedicated write path.
_STATUS_TO_OWNING_FIELD: dict[BUDStatus, str] = {
    status: field
    for field, status in FIELD_OWNING_STATUS.items()
    if status in _MCP_EDITABLE_PHASES
}

logger = structlog.get_logger(__name__)

# Per-field truncation for ``get_bud_by_id``. Bumped from the 5000-char
# cap in ``get_bud_context`` because the caller has asked for *this*
# specific BUD — they want the full content, not a list teaser.
_BUD_BY_ID_TRUNCATE = 10_000


def _parse_feature_ids(raw: Any) -> tuple[list[uuid_mod.UUID], list[str]]:
    """Coerce a caller-provided value into a list of UUIDs.

    Returns ``(valid_ids, dropped_raw)`` so the handler can log the
    LLM's typos / hallucinations without raising. Accepts a list of
    strings; anything else returns empty + a dropped marker so the
    handler can surface a soft error.
    """
    if raw is None:
        return [], []
    if not isinstance(raw, list):
        return [], ["<not a list>"]
    valid: list[uuid_mod.UUID] = []
    dropped: list[str] = []
    for entry in raw:
        try:
            valid.append(uuid_mod.UUID(str(entry)))
        except (ValueError, TypeError):
            dropped.append(str(entry))
    return valid, dropped


async def _wire_feature_links(
    db: AsyncSession,
    auth: MCPAuthResult,
    bud_id: uuid_mod.UUID,
    raw: Any,
) -> dict[str, int | list[str]]:
    """Persist the caller's ``linked_feature_ids`` array as BUDFeatureLink rows.

    The MCP write surface accepts an explicit ``linked_feature_ids``
    array (preferred over parsing the trailing JSON fence in the
    markdown body) so the LLM never has to fabricate the fence format.
    The repository's ``link_features`` is idempotent — already-linked
    features are skipped at the DB layer. ``source=MANUAL`` so the
    activity log distinguishes MCP-driven links from agent-driven
    ones.
    """
    valid_ids, dropped = _parse_feature_ids(raw)
    if not valid_ids and not dropped:
        return {"linked_count": 0, "dropped": []}

    accepted: list[uuid_mod.UUID] = []
    if valid_ids:
        link_repo = BUDFeatureLinkRepository(db, org_id=auth.org.id)
        accepted = await link_repo.link_features(
            bud_id,
            valid_ids,
            source=BUDFeatureLinkSource.MANUAL,
        )
    if dropped:
        logger.warning(
            "mcp_linked_feature_ids_dropped",
            bud_id=str(bud_id),
            dropped=dropped,
        )
    return {"linked_count": len(accepted), "dropped": dropped}


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

    # Explicit feature linkage — caller passes UUIDs they already
    # resolved via get_features. Replaces the brittle JSON-fence in
    # markdown the older REST flow relies on.
    link_summary = await _wire_feature_links(db, auth, bud.id, params.get("linked_feature_ids"))

    logger.info(
        "mcp_create_bud",
        org_id=str(auth.org.id),
        user_id=str(auth.user.id),
        token_id=str(auth.token_id) if auth.token_id else None,
        bud_id=str(bud.id),
        bud_number=next_number,
        linked_count=link_summary["linked_count"],
    )
    return {
        "success": True,
        "id": str(bud.id),
        "bud_number": next_number,
        "title": title,
        "linked_features": link_summary,
    }


async def _apply_design_content(
    db: AsyncSession,
    auth: MCPAuthResult,
    bud: BUDDocument,
    content: str,
) -> dict[str, Any]:
    """Persist DESIGN-phase content via the dedicated ``bud_designs`` upsert.

    BUD-level design (``repo_id=None``) is the single MCP-writable design
    row — the per-repo wireframe rows stay agent/UI-driven so the LLM
    can't accidentally overwrite a repo-specific design that's still
    being iterated on. Snapshot the prior HTML alongside the standard
    BUD snapshot so revert can restore both columns.
    """
    design_repo = BUDDesignRepository(db, org_id=auth.org.id)
    rows = await design_repo.list_for_bud(bud.id)
    prior_design = next((r for r in rows if r.repo_id is None), None)

    snapshot = build_snapshot(bud)
    snapshot["__design_html"] = prior_design.design_html if prior_design else None

    await bud_version_repo.commit_snapshot(
        db,
        bud_id=bud.id,
        phase=bud.status,
        snapshot=snapshot,
        source=BUDEditSource.MCP,
        edited_by=auth.user.id if auth.user else None,
        mcp_token_id=auth.token_id,
    )

    safe_html = sanitize_design_html(content)
    design = await design_repo.upsert(
        bud.id,
        None,
        design_html=safe_html,
        status=BUDDesignStatus.READY,
    )
    await db.flush()
    return {
        "success": True,
        "id": str(bud.id),
        "bud_number": bud.bud_number,
        "field": "design_html",
        "design_id": str(design.id),
        "phase": bud.status.value,
    }


async def _apply_markdown_content(
    db: AsyncSession,
    auth: MCPAuthResult,
    bud: BUDDocument,
    field: str,
    content: str,
) -> dict[str, Any]:
    """Persist a markdown content field via the standard snapshot+setattr path."""
    await bud_version_repo.insert_snapshot(
        db,
        bud=bud,
        phase=bud.status,
        source=BUDEditSource.MCP,
        edited_by=auth.user.id if auth.user else None,
        mcp_token_id=auth.token_id,
    )

    setattr(bud, field, content)

    # Embedding regenerates only when requirements_md changes — the
    # other markdown fields are downstream context the search pipeline
    # doesn't index, so paying the embed-roundtrip on every edit is
    # waste.
    if field == "requirements_md":
        try:
            bud.embedding = await embedding_service.embed(f"{bud.title} {content[:500]}")
        except Exception:
            logger.warning("mcp_update_bud_embedding_failed", bud_id=str(bud.id), exc_info=True)

    await db.flush()
    return {
        "success": True,
        "id": str(bud.id),
        "bud_number": bud.bud_number,
        "field": field,
        "phase": bud.status.value,
    }


async def handle_update_bud(
    db: AsyncSession,
    auth: MCPAuthResult,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Update content tied to the BUD's CURRENT phase.

    MCP writes are restricted to three creative phases — BUD (PRD),
    DESIGN (wireframe HTML), and TECH_ARCH (tech spec). The caller never
    names the field; the server resolves it from
    :data:`_MCP_EDITABLE_PHASES`. This both (a) mirrors the policy the
    UI shows and (b) forecloses an entire injection class where an LLM
    prompts another agent to "write tech_spec while in BUD phase".

    Guard order (fail-fast):

    1. token is per-user (no org-level writes)
    2. ``bud_id`` parses + BUD exists in the token's org
    3. ``bud.assignee_id == auth.user.id``
    4. BUD is not in a terminal phase
    5. ``bud.status`` is in :data:`_MCP_EDITABLE_PHASES`
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

    if bud.status not in _MCP_EDITABLE_PHASES:
        return _err(
            "phase_not_writable",
            (
                f"MCP writes are limited to the BUD, DESIGN, and TECH_ARCH phases. "
                f"BUD is currently in '{bud.status.value}'."
            ),
            current_status=bud.status.value,
        )

    content = str(params["content"])

    if bud.status == BUDStatus.DESIGN:
        result = await _apply_design_content(db, auth, bud, content)
    else:
        field = _STATUS_TO_OWNING_FIELD[bud.status]
        result = await _apply_markdown_content(db, auth, bud, field, content)

    # Same explicit-link path as create_bud. Linking happens AFTER the
    # content write so a failed write doesn't produce orphan link rows.
    # ``link_features`` is idempotent — re-passing existing ids is a
    # no-op, which makes update_bud safe to call with the same
    # ``linked_feature_ids`` on every edit.
    link_summary = await _wire_feature_links(db, auth, bud.id, params.get("linked_feature_ids"))
    result["linked_features"] = link_summary

    logger.info(
        "mcp_update_bud",
        org_id=str(auth.org.id),
        user_id=str(auth.user.id),
        token_id=str(auth.token_id) if auth.token_id else None,
        bud_id=str(bud_id),
        phase=bud.status.value,
        field=result.get("field"),
        content_len=len(content),
        linked_count=link_summary["linked_count"],
    )
    return result


async def handle_get_bud_by_id(
    db: AsyncSession,
    auth: MCPAuthResult,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Return full content for a single BUD, org-scoped.

    No assignee restriction on reads — a developer drafting a related
    BUD should be able to pull context from their teammate's in-flight
    work. The response includes:

    * ``caller_user_id`` — the user the MCP token represents, or
      ``None`` for org-level tokens. Lets the LLM detect at the
      pre-flight step whether the assignee check will pass without
      composing a body the server would only reject.
    * ``is_assignee`` — derived convenience flag (``True`` iff
      ``bud.assignee_id == caller_user_id``). Saves the LLM from
      string-comparing UUIDs in chat.
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

    caller_user_id = str(auth.user.id) if auth.user else None
    is_assignee = bool(
        caller_user_id is not None
        and bud.assignee_id is not None
        and str(bud.assignee_id) == caller_user_id
    )

    return {
        "id": str(bud.id),
        "bud_number": bud.bud_number,
        "title": bud.title,
        "status": bud.status.value,
        "assignee_id": str(bud.assignee_id) if bud.assignee_id else None,
        "caller_user_id": caller_user_id,
        "is_assignee": is_assignee,
        "requirements_md": _truncate(bud.requirements_md),
        "tech_spec_md": _truncate(bud.tech_spec_md),
        "test_plan_md": _truncate(bud.test_plan_md),
        "code_review_comments": bud.code_review_comments,
        "auto_generate_phases": bud.auto_generate_phases,
    }
