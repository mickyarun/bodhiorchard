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

"""MCP handlers for per-BUD wireframe read/write.

Replaces the path-based inlining of wireframe HTML in agent prompts. Agents
fetch the current design via ``get_bud_designs`` and write the iterated
result back via ``write_bud_design`` — DB becomes the single source of
truth, no temp files or stdout-JSON parsing involved.
"""

import uuid as uuid_mod
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.mcp.auth import MCPAuthResult
from app.mcp.handler_utils import require_non_empty
from app.models.bud import BUDDesignStatus
from app.models.organization import Organization
from app.repositories.bud import BUDDesignRepository
from app.services.bud_timeline import record_event
from app.services.html_sanitizer import sanitize_design_html

logger = structlog.get_logger(__name__)


async def handle_get_bud_designs(
    db: AsyncSession,
    org: Organization,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Return the wireframe(s) attached to a BUD.

    Two call shapes:

    * Scoped lookup — caller passes ``repo_id`` to fetch one specific
      row regardless of status. Used by the designer agent during
      iteration: it needs to read its own ``generating`` row to
      refine the existing HTML, so we deliberately bypass the
      ready-only filter here.
    * Cross-repo lookup — caller omits ``repo_id``. By default only
      ``status='ready'`` rows are returned (so tech-arch / code
      review / testing don't accidentally reason over empty
      ``design_html`` from a failed or in-flight row). The response
      reports a ``skipped_count`` of excluded non-ready rows along
      with their statuses, so callers can flag the gap in their
      output instead of silently writing around it. Set
      ``include_non_ready: true`` to opt back into the unfiltered
      behaviour.
    """
    error = require_non_empty(params, "bud_id")
    if error:
        return error

    try:
        bud_uuid = uuid_mod.UUID(params["bud_id"])
    except (ValueError, TypeError):
        return {"success": False, "error": "bud_id is not a valid UUID"}

    repo_filter: uuid_mod.UUID | None = None
    if params.get("repo_id"):
        try:
            repo_filter = uuid_mod.UUID(params["repo_id"])
        except (ValueError, TypeError):
            return {"success": False, "error": "repo_id is not a valid UUID"}

    include_non_ready = bool(params.get("include_non_ready", False))

    repo = BUDDesignRepository(db, org_id=org.id)
    rows = await repo.list_with_repo_names(bud_uuid, repo_id=repo_filter)

    skipped_statuses: list[str] = []
    kept: list[dict[str, Any]] = []
    apply_ready_filter = repo_filter is None and not include_non_ready

    for row in rows:
        raw_status = row["status"]
        status_str = (
            raw_status.value if isinstance(raw_status, BUDDesignStatus) else str(raw_status)
        )
        if apply_ready_filter and status_str != BUDDesignStatus.READY.value:
            skipped_statuses.append(status_str)
            continue
        kept.append(
            {
                "design_id": str(row["id"]),
                "repo_id": str(row["repo_id"]) if row["repo_id"] else None,
                "repo_name": row["repo_name"] or "general",
                "design_html": row["design_html"] or "",
                "notes": row["notes"] or "",
                "status": status_str,
                "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
            }
        )

    logger.info(
        "mcp_get_bud_designs",
        org_id=str(org.id),
        bud_id=str(bud_uuid),
        repo_id=str(repo_filter) if repo_filter else None,
        include_non_ready=include_non_ready,
        count=len(kept),
        skipped=len(skipped_statuses),
    )
    return {
        "designs": kept,
        "count": len(kept),
        "skipped_count": len(skipped_statuses),
        "skipped_statuses": skipped_statuses,
    }


async def handle_write_bud_design(
    db: AsyncSession,
    auth: MCPAuthResult,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Persist an iterated wireframe HTML for a BUD/repo design row.

    Sanitises the HTML, then updates the targeted ``bud_designs`` row
    and marks it ``READY``. Resolution priority:

    1. ``design_id`` (when supplied) — direct lookup by UUID. The row's
       ``bud_id`` and ``org_id`` must match the caller's context;
       mismatches return an error instead of writing. This is the path
       chat iteration uses so a stale prompt can't accidentally insert
       a fresh row.
    2. ``(bud_id, repo_id)`` upsert — the initial-generation path used
       by ``job_design`` when the row doesn't exist yet.

    ``notes`` are optional free-form override text.

    Records a ``design_updated`` timeline event crediting the MCP token
    owner so the designer "design contribution" SP rule can attribute the
    work at BUD close. Agent-driven writes (no token user) record the event
    with a NULL actor and are simply not credited.
    """
    org = auth.org
    error = require_non_empty(params, "bud_id", "html")
    if error:
        return error

    try:
        bud_uuid = uuid_mod.UUID(params["bud_id"])
    except (ValueError, TypeError):
        return {"success": False, "error": "bud_id is not a valid UUID"}

    repo_uuid: uuid_mod.UUID | None = None
    if params.get("repo_id"):
        try:
            repo_uuid = uuid_mod.UUID(params["repo_id"])
        except (ValueError, TypeError):
            return {"success": False, "error": "repo_id is not a valid UUID"}

    design_uuid: uuid_mod.UUID | None = None
    if params.get("design_id"):
        try:
            design_uuid = uuid_mod.UUID(params["design_id"])
        except (ValueError, TypeError):
            return {"success": False, "error": "design_id is not a valid UUID"}

    raw_html = params["html"]
    safe_html = sanitize_design_html(raw_html)
    notes = params.get("notes")

    repo = BUDDesignRepository(db, org_id=org.id)

    if design_uuid is not None:
        # Direct-update path. Verify the row belongs to the caller's
        # org and the claimed BUD before mutating — the org_id scope on
        # ``BUDDesignRepository`` already filters cross-org reads, but
        # the bud_id check is explicit so a stale chat job can't
        # silently land HTML on a different BUD's row.
        existing = await repo.get_by_id(design_uuid)
        if existing is None or existing.bud_id != bud_uuid:
            logger.warning(
                "mcp_write_bud_design_rejected",
                org_id=str(org.id),
                bud_id=str(bud_uuid),
                design_id=str(design_uuid),
                reason="design_id_not_found_or_bud_mismatch",
                row_exists=existing is not None,
            )
            return {
                "success": False,
                "error": (
                    f"design_id {design_uuid} not found for bud_id {bud_uuid}. "
                    "The row may have been deleted; ask the user to retry."
                ),
            }
        existing.design_html = safe_html
        existing.status = BUDDesignStatus.READY
        if notes is not None:
            existing.notes = notes
        await db.commit()
        design = existing
    else:
        design = await repo.upsert(
            bud_uuid,
            repo_uuid,
            design_html=safe_html,
            status=BUDDesignStatus.READY,
            notes=notes,
        )
        await db.commit()

    # Credit the human who iterated the design (NULL for agent-driven writes).
    await record_event(
        db,
        org.id,
        bud_uuid,
        "design_updated",
        actor_id=auth.user.id if auth.user else None,
        actor_name=auth.user.name if auth.user else None,
        detail={"source": "mcp"},
    )
    await db.commit()

    logger.info(
        "mcp_write_bud_design",
        org_id=str(org.id),
        bud_id=str(bud_uuid),
        repo_id=str(repo_uuid) if repo_uuid else None,
        design_id=str(design.id),
        html_length=len(safe_html),
        targeted_by_design_id=design_uuid is not None,
    )
    return {
        "saved": True,
        "design_id": str(design.id),
        "length": len(safe_html),
    }
