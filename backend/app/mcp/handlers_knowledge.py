"""MCP handlers for knowledge base, feature registry, and bug search.

Covers: get_knowledge, search_bugs, get_pending_features,
write_feature_registry, check_feature_exists, format_feature_content,
and code-location merge logic.
"""

from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge_item import KnowledgeItem
from app.models.organization import Organization
from app.repositories.knowledge_item import KnowledgeItemRepository
from app.services.embedding_service import embedding_service

logger = structlog.get_logger(__name__)


def format_feature_content(
    description: str,
    capabilities: list[str],
    source_clusters: list[str],
    *,
    feature_status: str | None = None,
    source_ref: str | None = None,
) -> str:
    """Format structured feature content for storage.

    Produces a lean plain-text block optimized for embedding search
    (description dominates vector), triage agent reading (capabilities),
    and token efficiency (~100-150 tokens).

    Code locations are stored on the junction table (knowledge_to_repo),
    not in the content text.

    Args:
        description: 1-2 sentence business description.
        capabilities: List of specific things the feature does.
        source_clusters: Cluster names (kept for signature compat).
        feature_status: Optional lifecycle status (planned/in_progress/implemented).
        source_ref: Optional BUD reference (e.g. "BUD-042").

    Returns:
        Formatted plain-text content string.
    """
    lines = [description, ""]

    if feature_status:
        status_label = feature_status.upper().replace("_", " ")
        lines.append(f"Status: {status_label}")
        if source_ref and feature_status != "implemented":
            lines.append(f"Source: {source_ref}")
        lines.append("")

    if capabilities:
        lines.append("Capabilities:")
        for cap in capabilities:
            lines.append(f"- {cap}")

    return "\n".join(lines)


async def _try_embed(title: str, content: str) -> list[float] | None:
    """Attempt to embed a feature inline. Returns None on failure."""
    try:
        return await embedding_service.embed(f"{title}\n{content}"[:2000])
    except Exception as exc:
        logger.warning("inline_embed_failed", title=title, error=str(exc))
        return None


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
    """Save a synthesized feature description and mark source clusters done.

    Supports upgrading PLANNED/IN_PROGRESS features to IMPLEMENTED when code
    is scanned. Uses exact-title match first, then falls back to semantic
    matching against planned items.
    """
    from app.mcp.synthesis_queue import get_queue_remaining, remove_from_queue

    feature_name = params["feature_name"]
    repo_name = params.get("repo_name")
    source_clusters = params.get("source_clusters", [])
    title = f"Feature: {feature_name}"

    content = format_feature_content(
        description=params["description"],
        capabilities=params["capabilities"],
        source_clusters=source_clusters,
        feature_status="implemented",
    )

    # Resolve repo_id from repo_name for FK link
    repo_id = None
    if repo_name:
        from app.repositories.tracked_repository import TrackedRepoRepository

        tr_repo = TrackedRepoRepository(db, org_id=org.id)
        tracked = await tr_repo.get_by_name(repo_name)
        if tracked:
            repo_id = tracked.id

    # 1. Try exact-title upsert
    ki_repo = KnowledgeItemRepository(db, org_id=org.id)
    item = await ki_repo.get_by_title_and_category(title, "feature_registry")
    upgraded_from = None

    if item:
        item.content = content
        item.source = "scan"
        item.tags = sorted(set(item.tags or []) | set(params["tags"]))[:10]
        item.embedding = await _try_embed(title, content)
        item.is_active = True
        item.feature_status = "implemented"
    else:
        # 2. Check for PLANNED/IN_PROGRESS items to upgrade via semantic match
        try:
            new_vector = await embedding_service.embed(f"{title}\n{content}"[:2000])
            match_rows = await ki_repo.find_nearest_by_status(
                new_vector,
                category="feature_registry",
                statuses=["planned", "in_progress"],
                limit=1,
            )
            if match_rows:
                matched_item, distance = match_rows[0]
                score = 1.0 - distance
                if score >= 0.7:
                    # Upgrade the planned item
                    upgraded_from = matched_item.feature_status
                    matched_item.title = title
                    matched_item.content = content
                    matched_item.source = "scan"
                    matched_item.tags = sorted(set(matched_item.tags or []) | set(params["tags"]))[
                        :10
                    ]
                    matched_item.embedding = await _try_embed(title, content)
                    matched_item.is_active = True
                    matched_item.feature_status = "implemented"
                    item = matched_item
                    logger.info(
                        "feature_upgraded_from_planned",
                        org_id=str(org.id),
                        source_ref=matched_item.source_ref,
                        score=round(score, 4),
                    )
        except Exception:
            logger.warning("feature_semantic_match_failed", org_id=str(org.id))

        # 3. No match found — create new
        if item is None:
            item = KnowledgeItem(
                org_id=org.id,
                category="feature_registry",
                title=title,
                content=content,
                source="scan",
                tags=params["tags"],
                is_active=True,
                feature_status="implemented",
                embedding=await _try_embed(title, content),
            )
            await ki_repo.add(item)

    await ki_repo.flush()

    # Link to repo via junction table (with per-repo code_locations)
    if repo_id and item:
        await ki_repo.link_to_repo(
            item.id, repo_id, code_locations=params.get("code_locations")
        )
        await ki_repo.flush()

    # Deactivate originals when merging cross-repo features.
    # First, transfer repo links from source features to the merged feature
    # so cross-repo associations survive the merge.
    # Uses bulk SQL UPDATE (not ORM load+modify) so concurrent calls
    # are idempotent — if another request already deactivated the rows,
    # this UPDATE matches 0 rows instead of raising StaleDataError.
    merge_source_titles = params.get("merge_source_titles", [])
    merged_deactivated = 0
    if merge_source_titles:
        # Transfer repo links from source features before deactivating them
        if item:
            source_items = await ki_repo.get_active_by_titles(
                merge_source_titles, "feature_registry"
            )
            if source_items:
                transferred = await ki_repo.transfer_repo_links(
                    [s.id for s in source_items], item.id
                )
                if transferred:
                    await ki_repo.flush()
                    logger.info(
                        "merge_repo_links_transferred",
                        merged_title=title,
                        source_count=len(source_items),
                        repo_ids_transferred=transferred,
                    )

        merged_deactivated = await ki_repo.bulk_deactivate_by_titles(
            merge_source_titles, "feature_registry"
        )

    # Mark source clusters as done in the tracker
    if source_clusters:
        remove_from_queue(str(org.id), source_clusters)

    remaining = len(get_queue_remaining(str(org.id)))
    result_data: dict[str, Any] = {
        "success": True,
        "title": title,
        "remaining_clusters": remaining,
    }
    if upgraded_from:
        result_data["upgraded_from"] = upgraded_from
    if merged_deactivated:
        result_data["merged_deactivated"] = merged_deactivated

    logger.info(
        "mcp_write_feature_registry",
        org_id=str(org.id),
        title=title,
        remaining=remaining,
        upgraded_from=upgraded_from,
        merged_deactivated=merged_deactivated,
    )
    return result_data


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


async def handle_merge_features(
    db: AsyncSession,
    org: Organization,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Merge duplicate features across repos.

    Keeps the feature with ``keep_title``, deactivates features in
    ``merge_titles``, and links the kept feature to all specified repos.
    """
    keep_title = params["keep_title"]
    merge_titles = params.get("merge_titles", [])
    repo_names = params.get("repo_names", [])

    ki_repo = KnowledgeItemRepository(db, org_id=org.id)

    # 1. Find the feature to keep
    item = await ki_repo.get_by_title_and_category(keep_title, "feature_registry")
    if not item:
        return {"success": False, "error": f"Feature not found: {keep_title}"}

    # 2. Transfer repo links from merge sources, then deactivate them
    merged_count = 0
    if merge_titles:
        source_items = await ki_repo.get_active_by_titles(merge_titles, "feature_registry")
        if source_items:
            await ki_repo.transfer_repo_links([s.id for s in source_items], item.id)
            merged_count = await ki_repo.bulk_deactivate_by_titles(
                merge_titles, "feature_registry"
            )
            await ki_repo.flush()

    # 3. Link to all specified repos
    repos_linked = 0
    if repo_names:
        from app.repositories.tracked_repository import TrackedRepoRepository

        tr_repo = TrackedRepoRepository(db, org_id=org.id)
        for rname in repo_names:
            tracked = await tr_repo.get_by_name(rname)
            if tracked:
                await ki_repo.link_to_repo(item.id, tracked.id)
                repos_linked += 1

    await ki_repo.flush()

    if merged_count == 0 and repos_linked == 0:
        logger.info("mcp_merge_features_noop", org_id=str(org.id), kept=keep_title)
        return {
            "success": True,
            "kept": keep_title,
            "merged_count": 0,
            "repos_linked": 0,
            "warning": "No changes made — nothing to merge or link",
        }

    logger.info(
        "mcp_merge_features",
        org_id=str(org.id),
        kept=keep_title,
        merged=merged_count,
        repos_linked=repos_linked,
    )
    return {
        "success": True,
        "kept": keep_title,
        "merged_count": merged_count,
        "repos_linked": repos_linked,
    }
