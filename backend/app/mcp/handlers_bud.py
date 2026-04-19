# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""MCP handlers for BUD document operations.

Covers: get_bud_context, write_bud.
"""

from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

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
    """Save or update a BUD document."""
    title = params.get("title", "")
    content = params.get("content", "")
    bud_number = params.get("bud_number")

    if not title:
        return {"success": False, "error": "title is required"}

    bud_repo = BUDRepository(db, org_id=org.id)

    # Update existing BUD if bud_number is provided
    if bud_number is not None:
        existing = await bud_repo.get_by_number(int(bud_number))
        if existing is None:
            return {"success": False, "error": f"BUD-{bud_number:03d} not found"}

        existing.title = title
        existing.requirements_md = content
        logger.info(
            "mcp_update_bud",
            org_id=str(org.id),
            bud_number=bud_number,
            title=title,
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
        requirements_md=content,
    )
    await bud_repo.create(bud)

    # Create a PLANNED feature_registry entry for immediate discoverability
    from app.services.feature_lifecycle import create_planned_feature

    feature_item = await create_planned_feature(db, org.id, next_number, title, content)

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
    db: AsyncSession, org_id: Any, task_id: str,
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
