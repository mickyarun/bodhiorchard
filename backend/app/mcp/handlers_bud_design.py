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

from app.mcp.handler_utils import require_non_empty
from app.models.bud import BUDDesignStatus
from app.models.organization import Organization
from app.repositories.bud import BUDDesignRepository
from app.services.html_sanitizer import sanitize_design_html

logger = structlog.get_logger(__name__)


async def handle_get_bud_designs(
    db: AsyncSession,
    org: Organization,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Return the wireframe(s) attached to a BUD.

    Filters to a single repo if ``repo_id`` is supplied — otherwise returns
    every per-repo design row for the BUD, ordered by creation time.
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

    repo = BUDDesignRepository(db, org_id=org.id)
    rows = await repo.list_with_repo_names(bud_uuid, repo_id=repo_filter)

    designs = [
        {
            "design_id": str(row["id"]),
            "repo_id": str(row["repo_id"]) if row["repo_id"] else None,
            "repo_name": row["repo_name"] or "general",
            "design_html": row["design_html"] or "",
            "notes": row["notes"] or "",
            "status": (
                row["status"].value
                if isinstance(row["status"], BUDDesignStatus)
                else str(row["status"])
            ),
            "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
        }
        for row in rows
    ]

    logger.info(
        "mcp_get_bud_designs",
        org_id=str(org.id),
        bud_id=str(bud_uuid),
        repo_id=str(repo_filter) if repo_filter else None,
        count=len(designs),
    )
    return {"designs": designs, "count": len(designs)}


async def handle_write_bud_design(
    db: AsyncSession,
    org: Organization,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Persist an iterated wireframe HTML for a BUD/repo design row.

    Sanitises the HTML, upserts the ``bud_designs`` row keyed by
    ``(bud_id, repo_id)``, and marks it ``READY``. ``notes`` are optional
    free-form override text shown alongside the wireframe.
    """
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

    raw_html = params["html"]
    safe_html = sanitize_design_html(raw_html)
    notes = params.get("notes")

    repo = BUDDesignRepository(db, org_id=org.id)
    design = await repo.upsert(
        bud_uuid,
        repo_uuid,
        design_html=safe_html,
        status=BUDDesignStatus.READY,
        notes=notes,
    )
    await db.commit()

    logger.info(
        "mcp_write_bud_design",
        org_id=str(org.id),
        bud_id=str(bud_uuid),
        repo_id=str(repo_uuid) if repo_uuid else None,
        design_id=str(design.id),
        html_length=len(safe_html),
    )
    return {
        "saved": True,
        "design_id": str(design.id),
        "length": len(safe_html),
    }
