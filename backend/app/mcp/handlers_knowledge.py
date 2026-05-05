# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""MCP handlers for knowledge base, feature registry, and bug search.

Covers: get_knowledge, search_bugs, get_pending_features,
write_feature_registry, check_feature_exists, and code-location merge logic.

Feature-content formatting and inline embedding live in
``app/services/feature_content.py`` so the merge writer service can
share them without importing from the MCP layer.
"""

from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.mcp.handler_utils import require_non_empty
from app.models.organization import Organization
from app.repositories.knowledge_item import KnowledgeItemRepository
from app.services.embedding_service import embedding_service
from app.services.feature_content import format_feature_content
from app.services.feature_content import try_embed as _try_embed

logger = structlog.get_logger(__name__)

# Re-export for legacy callers (handlers_scan imports these names).
__all__ = ["format_feature_content", "_try_embed"]


async def handle_get_knowledge(
    db: AsyncSession,
    org: Organization,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Query knowledge base via semantic search (pgvector)."""
    query = params.get("query", "")
    limit = min(params.get("limit", 10), 50)
    category = params.get("category")

    if not query:
        return {"results": [], "error": "query is required"}

    try:
        vector = await embedding_service.embed(query)
    except Exception:
        logger.exception("mcp_get_knowledge_embed_failed", query=query[:100])
        return {"results": [], "error": "Embedding service unavailable"}

    ki_repo = KnowledgeItemRepository(db, org_id=org.id)
    rows = await ki_repo.semantic_search(vector, category=category, limit=limit)

    return {
        "results": [
            {
                "title": item.title,
                "content": item.content or "",
                "category": item.category,
                "score": round(1.0 - distance, 4),
                "source_ref": item.source_ref,
            }
            for item, distance in rows
        ],
    }


async def handle_search_bugs(
    db: AsyncSession,
    org: Organization,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Search bugs by description using semantic search."""
    from app.repositories.bug import BugRepository

    query = params.get("query", "")
    bug_status = params.get("status", "open")
    limit = min(params.get("limit", 10), 50)

    bug_repo = BugRepository(db, org_id=org.id)
    bugs = await bug_repo.search_by_status(status_filter=bug_status, limit=limit)

    logger.info("mcp_search_bugs", org_id=str(org.id), query=query[:100], found=len(bugs))
    return {
        "bugs": [
            {
                "id": str(bug.id),
                "title": bug.title,
                "description": (bug.description or "")[:1000],
                "severity": bug.severity.value if bug.severity else "medium",
                "status": bug.status.value if bug.status else "open",
                "module": bug.module,
            }
            for bug in bugs
        ],
    }


async def handle_get_pending_features(
    db: AsyncSession,
    org: Organization,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Return the next batch of clusters awaiting feature synthesis."""
    from app.mcp.synthesis_queue import get_queue_remaining

    batch_size = min(params.get("batch_size", 5), 10)
    remaining = get_queue_remaining(str(org.id))
    batch = remaining[:batch_size]
    return {
        "clusters": batch,
        "remaining_count": len(remaining),
        "batch_size": len(batch),
        "done": len(remaining) == 0,
    }


async def handle_write_feature_registry(
    db: AsyncSession,
    org: Organization,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Stage one synthesized feature into ``synthesized_features``.

    Per-repo synthesis is staging-only: this handler appends an
    immutable pre-merge row and dequeues the cluster, but does NOT
    touch ``knowledge_items`` or ``knowledge_to_repo``. The merge phase
    (B3) is the sole writer of canonical KIs.
    """
    from app.mcp.synth_feature_writer import persist_synth_feature
    from app.mcp.synthesis_queue import get_queue_remaining, remove_from_queue
    from app.repositories.tracked_repository import TrackedRepoRepository

    error = require_non_empty(
        params,
        "feature_name",
        "description",
        "capabilities",
        "tags",
    )
    if error:
        return error

    feature_name = params["feature_name"]
    repo_name = params.get("repo_name")
    source_clusters = params.get("source_clusters", [])
    title = f"Feature: {feature_name}"

    if not repo_name:
        return {
            "success": False,
            "error": (
                "repo_name is required so the synth row can be bound to a tracked repository."
            ),
        }

    tr_repo = TrackedRepoRepository(db, org_id=org.id)
    tracked = await tr_repo.get_by_name(repo_name)
    if tracked is None:
        return {
            "success": False,
            "error": (
                f"Unknown repo_name: {repo_name!r}. Call the tool again with "
                "one of the org's active tracked repository names."
            ),
        }
    repo_id = tracked.id

    await persist_synth_feature(
        db=db,
        org=org,
        repo_id=repo_id,
        feature_title=title,
        description=params["description"],
        capabilities=params["capabilities"],
        cluster_names=source_clusters,
        code_locations=params.get("code_locations"),
        tags=list(params.get("tags") or []),
    )

    if source_clusters:
        remove_from_queue(str(org.id), source_clusters)

    remaining = len(get_queue_remaining(str(org.id)))
    logger.info(
        "mcp_write_feature_registry",
        org_id=str(org.id),
        title=title,
        repo=repo_name,
        remaining=remaining,
    )
    return {"success": True, "title": title, "remaining_clusters": remaining}


async def handle_check_feature_exists(
    db: AsyncSession,
    org: Organization,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Check if a feature exists via semantic search over feature_registry items."""
    query = params["feature_description"]
    threshold = params.get("threshold", 0.6)

    try:
        vector = await embedding_service.embed(query)
    except Exception:
        logger.exception("check_feature_embed_failed", query=query[:100])
        return {"exists": False, "feature_count": 0, "features": [], "error": "Embedding failed"}

    ki_repo = KnowledgeItemRepository(db, org_id=org.id)
    rows = await ki_repo.semantic_search(vector, category="feature_registry", limit=5)

    features = []
    for item, distance in rows:
        score = round(1.0 - distance, 4)
        if score < threshold:
            continue
        features.append(
            {
                "title": item.title,
                "content": item.content,
                "score": score,
                "match_strength": "strong" if score >= 0.85 else "partial",
                "feature_status": item.feature_status or "implemented",
                "source_ref": item.source_ref,
            }
        )

    return {
        "exists": len(features) > 0,
        "feature_count": len(features),
        "features": features,
    }
