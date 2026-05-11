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

"""MCP handlers for BUD document operations.

Covers: get_bud_context, write_bud.
"""

from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.mcp.handler_utils import require_non_empty
from app.models.bud import BUDDocument, BUDStatus
from app.models.organization import Organization
from app.repositories.bud import BUDRepository

logger = structlog.get_logger(__name__)


async def handle_get_bud_context(
    db: AsyncSession,
    org: Organization,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Retrieve existing BUDs for context."""
    limit = min(params.get("limit", 5), 20)

    bud_repo = BUDRepository(db, org_id=org.id)
    buds = await bud_repo.list_buds(limit=limit)

    return {
        "buds": [
            {
                "id": str(bud.id),
                "bud_number": bud.bud_number,
                "title": bud.title,
                "status": bud.status.value if bud.status else "bud",
                "requirements_md": (bud.requirements_md or "")[:5000],
            }
            for bud in buds
        ],
    }


async def handle_write_bud(
    db: AsyncSession,
    org: Organization,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Save or update a BUD document.

    Accepts the Markdown body under either ``requirements_md`` (matches
    the DB column and the prompt context the agent sees) or ``content``
    (the older name still declared in the MCP tool schema). Claude's
    tool-call serialization has historically flipped between the two;
    accepting either keeps the handler robust to that drift.

    Refuses empty bodies — silently clobbering an existing BUD's
    ``requirements_md`` with ``""`` is how we shipped data loss in the
    first place.
    """
    # Canonical contract: the schema declares `requirements_md`
    # (matching the DB column) as the required body field. If Claude
    # sends anything else, we surface a loud error rather than clobber
    # the existing BUD with an empty string — which is how the silent-
    # data-loss bug shipped in the first place.
    error = require_non_empty(params, "title", "requirements_md")
    if error:
        return error

    title = params.get("title", "")
    body = params.get("requirements_md", "")
    bud_number = params.get("bud_number")

    bud_repo = BUDRepository(db, org_id=org.id)

    # Update existing BUD if bud_number is provided
    if bud_number is not None:
        existing = await bud_repo.get_by_number(int(bud_number))
        if existing is None:
            return {"success": False, "error": f"BUD-{bud_number:03d} not found"}

        existing.title = title
        existing.requirements_md = body
        logger.info(
            "mcp_update_bud",
            org_id=str(org.id),
            bud_number=bud_number,
            title=title,
            body_len=len(body),
        )
        return {
            "success": True,
            "id": str(existing.id),
            "bud_number": bud_number,
            "title": title,
            "updated": True,
        }

    # Create new BUD
    next_number = await bud_repo.next_bud_number()

    bud = BUDDocument(
        org_id=org.id,
        bud_number=next_number,
        title=title,
        status=BUDStatus.BUD,
        requirements_md=body,
    )
    await bud_repo.create(bud)

    # Create a PLANNED feature_registry entry for immediate discoverability
    from app.services.feature_lifecycle import create_planned_feature

    feature_item = await create_planned_feature(db, org.id, next_number, title, body)

    logger.info("mcp_write_bud", org_id=str(org.id), bud_number=next_number, title=title)
    return {
        "success": True,
        "id": str(bud.id),
        "bud_number": next_number,
        "title": title,
        "feature_created": True,
        "feature_title": feature_item.title,
    }


async def _resolve_bud(
    db: AsyncSession,
    org_id: Any,
    task_id: str,
) -> BUDDocument | None:
    """Resolve a BUD from a task_id (BUD number string or UUID)."""
    import uuid

    bud_repo = BUDRepository(db, org_id=org_id)

    # Try as BUD number first (most common from developer CLI)
    try:
        bud_number = int(task_id)
        bud = await bud_repo.get_by_number(bud_number)
        if bud:
            return bud
    except (ValueError, TypeError):
        pass

    # Try as UUID
    try:
        bud_id = uuid.UUID(task_id)
        return await bud_repo.get_by_id(bud_id)
    except (ValueError, TypeError):
        pass

    return None
