"""MCP (Model Context Protocol) server for Bodhigrove.

Exposes tools that Claude Code can call to read/write Bodhigrove data:
BUDs, knowledge base, bugs, task status, team context.

Mounted at /mcp/ on the main FastAPI app.
"""

from typing import Any

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.encryption import decrypt_secret
from app.mcp.auth import verify_mcp_token
from app.models.bud import BUDDocument, BUDStatus
from app.models.knowledge_item import KnowledgeItem
from app.models.organization import Organization
from app.repositories.bud import BUDRepository
from app.repositories.bug import BugRepository
from app.repositories.knowledge_item import KnowledgeItemRepository
from app.repositories.skill_profile import SkillProfileRepository
from app.services.embedding_service import embedding_service

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/mcp", tags=["mcp"])


# --- Feature Synthesis Queue (in-memory tracker) ---

# Pending clusters for feature synthesis, keyed by queue_key (str).
# queue_key is "org_id" for single-repo or "org_id:repo_name" for parallel.
# Set by scan pipeline before calling Claude Code, consumed by MCP tools.
_synthesis_queue: dict[str, list[dict]] = {}

# Maps org_id → list of active queue keys (for parallel repo support).
# When get_pending_features is called with just org_id, it checks all
# active queues for that org and returns from the first non-empty one.
_active_queue_keys: dict[str, list[str]] = {}


def set_synthesis_queue(
    org_id: str,
    clusters: list[dict],
    *,
    repo_name: str | None = None,
) -> str:
    """Populate the synthesis queue with clusters to process.

    Returns:
        The queue key used (for passing to clear_synthesis_queue).
    """
    queue_key = f"{org_id}:{repo_name}" if repo_name else org_id
    _synthesis_queue[queue_key] = clusters
    _active_queue_keys.setdefault(org_id, [])
    if queue_key not in _active_queue_keys[org_id]:
        _active_queue_keys[org_id].append(queue_key)
    return queue_key


def remove_from_queue(org_id: str, cluster_names: list[str]) -> None:
    """Remove processed clusters from all active queues for the org."""
    names_set = set(cluster_names)
    for key in _active_queue_keys.get(org_id, []):
        if key in _synthesis_queue:
            _synthesis_queue[key] = [
                c for c in _synthesis_queue[key] if c["name"] not in names_set
            ]


def get_queue_remaining(org_id: str, *, queue_key: str | None = None) -> list[dict]:
    """Return clusters still pending synthesis.

    If queue_key is given, return from that specific queue.
    Otherwise, aggregate remaining from all active queues for the org.
    """
    if queue_key:
        return _synthesis_queue.get(queue_key, [])
    remaining: list[dict] = []
    for key in _active_queue_keys.get(org_id, []):
        remaining.extend(_synthesis_queue.get(key, []))
    return remaining


def clear_synthesis_queue(org_id: str, *, queue_key: str | None = None) -> None:
    """Remove entries after synthesis completes.

    If queue_key is given, clear only that queue. Otherwise clear all for the org.
    """
    if queue_key:
        _synthesis_queue.pop(queue_key, None)
        keys = _active_queue_keys.get(org_id, [])
        if queue_key in keys:
            keys.remove(queue_key)
    else:
        for key in _active_queue_keys.pop(org_id, []):
            _synthesis_queue.pop(key, None)


# --- MCP Tool Definitions ---


class MCPToolDefinition(BaseModel):
    """Schema for an MCP tool definition."""

    name: str
    description: str
    input_schema: dict[str, Any]


class MCPToolCallRequest(BaseModel):
    """Request body for an MCP tool call."""

    params: dict[str, Any] = {}


MCP_TOOLS: list[MCPToolDefinition] = [
    MCPToolDefinition(
        name="get_bud_context",
        description="Retrieve existing BUDs for context when generating new ones",
        input_schema={
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "Project ID to fetch BUDs for"},
                "limit": {"type": "integer", "description": "Max BUDs to return", "default": 5},
            },
        },
    ),
    MCPToolDefinition(
        name="write_bud",
        description=(
            "Save or update a BUD document. If bud_number is provided, updates "
            "that existing BUD. Otherwise creates a new one."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "content": {"type": "string"},
                "bud_number": {
                    "type": "integer",
                    "description": "Existing BUD number to update (omit to create new)",
                },
                "backlog_item_id": {"type": "string"},
            },
            "required": ["title", "content"],
        },
    ),
    MCPToolDefinition(
        name="get_knowledge",
        description="Query the organization knowledge base via semantic search",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "limit": {"type": "integer", "default": 10},
                "category": {
                    "type": "string",
                    "description": "Category filter: feature_registry",
                },
            },
            "required": ["query"],
        },
    ),
    MCPToolDefinition(
        name="get_pending_features",
        description=(
            "Get the next batch of code clusters that need feature descriptions. "
            "Returns up to 5 clusters at a time with their file lists. "
            "Call this repeatedly until it returns an empty list."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "batch_size": {
                    "type": "integer",
                    "description": "How many clusters to return (default 5)",
                    "default": 5,
                },
            },
        },
    ),
    MCPToolDefinition(
        name="write_feature_registry",
        description=(
            "Save a synthesized feature description to the knowledge base. "
            "Also marks the source clusters as processed in the tracker. "
            "After calling this, call get_pending_features for the next batch."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "feature_name": {
                    "type": "string",
                    "description": "Human-readable feature name, e.g. 'Card Payments'",
                },
                "description": {
                    "type": "string",
                    "description": ("1-2 sentence business description of what this feature does"),
                },
                "capabilities": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "3-6 specific things this feature does",
                },
                "code_locations": {
                    "type": "object",
                    "description": (
                        "Map of layer to file paths, e.g. {backend: [...], frontend: [...]}"
                    ),
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "2-5 lowercase search keywords",
                },
                "source_clusters": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Cluster names this feature was synthesized from",
                },
                "repo_name": {
                    "type": "string",
                    "description": "Repository name (links feature to tracked repo)",
                },
                "merge_source_titles": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Titles of repo-specific features being merged. "
                        "Those items will be deactivated after the merged feature is saved."
                    ),
                },
            },
            "required": [
                "feature_name",
                "description",
                "capabilities",
                "code_locations",
                "tags",
            ],
        },
    ),
    MCPToolDefinition(
        name="check_feature_exists",
        description=(
            "Check if a feature already exists in the codebase. "
            "Returns matching features with descriptions, lifecycle status "
            "(planned/in_progress/implemented), and code locations. "
            "Use this before creating new features/BUDs to avoid duplication."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "feature_description": {
                    "type": "string",
                    "description": "Plain-English description of the feature to check",
                },
                "threshold": {
                    "type": "number",
                    "description": "Min similarity (0-1). Default 0.6",
                    "default": 0.6,
                },
            },
            "required": ["feature_description"],
        },
    ),
    MCPToolDefinition(
        name="search_bugs",
        description="Find bugs related to a given description or area",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "status": {"type": "string", "enum": ["open", "closed", "all"], "default": "open"},
                "limit": {"type": "integer", "default": 10},
            },
            "required": ["query"],
        },
    ),
    MCPToolDefinition(
        name="update_task_status",
        description="Report task progress back to Bodhigrove",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {"type": "string"},
                "status": {
                    "type": "string",
                    "enum": ["in_progress", "completed", "failed", "blocked"],
                },
                "message": {"type": "string"},
            },
            "required": ["task_id", "status"],
        },
    ),
    MCPToolDefinition(
        name="post_slack_message",
        description="Post a message to a Slack channel or thread",
        input_schema={
            "type": "object",
            "properties": {
                "channel": {"type": "string"},
                "message": {"type": "string"},
                "thread_ts": {"type": "string", "description": "Thread timestamp for replies"},
            },
            "required": ["channel", "message"],
        },
    ),
    MCPToolDefinition(
        name="get_team_context",
        description="Read team capacity, active work, and skill profiles",
        input_schema={
            "type": "object",
            "properties": {
                "team_id": {
                    "type": "string",
                    "description": "Team ID (optional, defaults to all)",
                },
            },
        },
    ),
    MCPToolDefinition(
        name="list_design_systems",
        description=(
            "List all extracted design systems for the organization. "
            "Returns repo names, IDs, and which is the default — without "
            "the full content. Call get_design_system with a specific "
            "repo_id to fetch the full content."
        ),
        input_schema={
            "type": "object",
            "properties": {},
        },
    ),
    MCPToolDefinition(
        name="get_design_system",
        description=(
            "Retrieve the full extracted design system (colors, typography, "
            "components, CDN boilerplate) for a specific repository or the "
            "organization default. Call list_design_systems first to see "
            "what's available."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "repo_id": {
                    "type": "string",
                    "description": (
                        "Repository UUID to get the design system for. "
                        "Omit to get the organization default."
                    ),
                },
            },
        },
    ),
]


@router.get("/tools")
async def list_tools() -> list[MCPToolDefinition]:
    """List all available MCP tools.

    This endpoint is called by Claude Code during MCP discovery.

    Returns:
        List of tool definitions with names, descriptions, and input schemas.
    """
    return MCP_TOOLS


@router.post("/tools/{tool_name}")
async def call_tool(
    tool_name: str,
    body: MCPToolCallRequest,
    db: AsyncSession = Depends(get_db),
    org: Organization = Depends(verify_mcp_token),
) -> dict[str, Any]:
    """Execute an MCP tool call from Claude Code.

    Args:
        tool_name: The name of the tool to execute.
        body: Tool call parameters.
        db: The async database session.
        org: The authenticated organization.

    Returns:
        Tool execution result.
    """
    logger.info(
        "mcp_tool_call",
        tool=tool_name,
        org_id=str(org.id),
        params=body.params,
    )

    handler = TOOL_HANDLERS.get(tool_name)
    if handler is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown tool: {tool_name}",
        )

    return await handler(db, org, body.params)


# --- Tool Handlers ---


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


async def handle_update_task_status(
    db: AsyncSession,
    org: Organization,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Update task/agent log status."""
    task_id = params.get("task_id", "")
    task_status = params.get("status", "")
    message = params.get("message", "")

    logger.info(
        "mcp_update_task_status",
        org_id=str(org.id),
        task_id=task_id,
        status=task_status,
        message=message[:200],
    )
    return {"success": True, "message": f"Task {task_id} updated to {task_status}"}


async def handle_post_slack_message(
    db: AsyncSession,
    org: Organization,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Post message to Slack via stored bot token."""
    channel = params.get("channel", "")
    message = params.get("message", "")
    thread_ts = params.get("thread_ts")

    bot_token = decrypt_secret(org.slack_bot_token or "")
    if not bot_token:
        return {"success": False, "error": "Slack bot token not configured for this organization"}

    payload: dict[str, str] = {
        "channel": channel,
        "text": message,
    }
    if thread_ts:
        payload["thread_ts"] = thread_ts

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                "https://slack.com/api/chat.postMessage",
                json=payload,
                headers={"Authorization": f"Bearer {bot_token}"},
            )
            data = resp.json()
            if not data.get("ok"):
                logger.warning("slack_post_failed", error=data.get("error"))
                return {"success": False, "error": data.get("error", "Slack API error")}
    except Exception:
        logger.exception("slack_post_exception", channel=channel)
        return {"success": False, "error": "Failed to connect to Slack API"}

    logger.info("mcp_post_slack", org_id=str(org.id), channel=channel)
    return {"success": True, "channel": channel}


async def handle_get_team_context(
    db: AsyncSession,
    org: Organization,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Read team capacity and skill profiles."""
    sp_repo = SkillProfileRepository(db, org_id=org.id)
    rows = await sp_repo.list_with_users()

    # Group by user
    team: dict[str, dict[str, Any]] = {}
    for profile, user in rows:
        key = str(profile.user_id) if profile.user_id else "unknown"
        if key not in team:
            team[key] = {
                "user_name": user.name if user else "Unknown",
                "email": user.email if user else "",
                "role": getattr(user, "role", "").value if getattr(user, "role", None) else "",
                "modules": [],
            }
        team[key]["modules"].append(
            {
                "name": profile.module,
                "score": float(profile.skill_score),
                "languages": profile.languages or [],
                "touch_count": profile.touch_count,
            }
        )

    logger.info("mcp_get_team_context", org_id=str(org.id), members=len(team))
    return {"team": list(team.values())}


def format_feature_content(
    description: str,
    capabilities: list[str],
    code_locations: dict[str, Any],
    source_clusters: list[str],
    *,
    feature_status: str | None = None,
    source_ref: str | None = None,
) -> str:
    """Format structured feature content for storage.

    Produces a lean plain-text block optimized for embedding search
    (description dominates vector), triage agent reading (capabilities),
    and token efficiency (~100-150 tokens).

    Code locations and cluster names are intentionally omitted — agents
    can look those up live via GitNexus tools when needed.

    Args:
        description: 1-2 sentence business description.
        capabilities: List of specific things the feature does.
        code_locations: Map of layer → file paths (kept for signature compat).
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


async def handle_get_pending_features(
    db: AsyncSession,
    org: Organization,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Return the next batch of clusters awaiting feature synthesis."""
    batch_size = min(params.get("batch_size", 5), 10)
    remaining = get_queue_remaining(str(org.id))
    batch = remaining[:batch_size]
    return {
        "clusters": batch,
        "remaining_count": len(remaining),
        "batch_size": len(batch),
        "done": len(remaining) == 0,
    }


def _merge_code_locations(
    existing: dict[str, Any] | None, incoming: dict[str, Any] | None
) -> dict[str, list[str]]:
    """Merge two code_locations dicts, unioning paths per layer (O(n) per layer)."""
    merged: dict[str, list[str]] = {}
    all_layers = set((existing or {}).keys()) | set((incoming or {}).keys())
    for layer in sorted(all_layers):
        existing_paths = (existing or {}).get(layer, [])
        incoming_paths = (incoming or {}).get(layer, [])
        seen: set[str] = set(existing_paths)
        result = list(existing_paths)
        for p in incoming_paths:
            if p not in seen:
                seen.add(p)
                result.append(p)
        merged[layer] = result
    return merged


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
    feature_name = params["feature_name"]
    repo_name = params.get("repo_name")
    source_clusters = params.get("source_clusters", [])
    title = f"Feature: {feature_name}"

    content = format_feature_content(
        description=params["description"],
        capabilities=params["capabilities"],
        code_locations=params["code_locations"],
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
        item.embedding = None  # Reset for re-embedding
        item.is_active = True
        item.feature_status = "implemented"
        item.code_locations = _merge_code_locations(
            item.code_locations, params.get("code_locations")
        )
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
                    matched_item.embedding = None  # Reset for re-embedding
                    matched_item.is_active = True
                    matched_item.feature_status = "implemented"
                    matched_item.code_locations = _merge_code_locations(
                        matched_item.code_locations, params.get("code_locations")
                    )
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
                code_locations=params.get("code_locations") or {},
            )
            await ki_repo.add(item)

    await ki_repo.flush()

    # Link to repo via junction table
    if repo_id and item:
        await ki_repo.link_to_repo(item.id, repo_id)
        await ki_repo.flush()

    # Deactivate originals when merging cross-repo features.
    # Uses bulk SQL UPDATE (not ORM load+modify) so concurrent calls
    # are idempotent — if another request already deactivated the rows,
    # this UPDATE matches 0 rows instead of raising StaleDataError.
    merge_source_titles = params.get("merge_source_titles", [])
    merged_deactivated = 0
    if merge_source_titles:
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


async def handle_list_design_systems(
    db: AsyncSession,
    org: Organization,
    params: dict[str, Any],
) -> dict[str, Any]:
    """List all extracted design systems (metadata only, no content)."""
    from app.repositories.design_system import DesignSystemRefRepository

    ds_repo = DesignSystemRefRepository(db, org_id=org.id)
    rows = await ds_repo.list_with_repo_names()

    logger.info("mcp_list_design_systems", org_id=str(org.id), count=len(rows))
    return {
        "design_systems": [
            {
                "repo_id": str(row["repo_id"]),
                "repo_name": row["repo_name"] or "Unknown",
                "is_default": row["is_default"],
                "extracted_at": row["extracted_at"].isoformat() if row["extracted_at"] else None,
                "content_length": len(row["content"] or ""),
            }
            for row in rows
        ],
        "count": len(rows),
    }


async def handle_get_design_system(
    db: AsyncSession,
    org: Organization,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Retrieve the full design system for a repo or the org default."""
    from app.repositories.design_system import DesignSystemRefRepository

    ds_repo = DesignSystemRefRepository(db, org_id=org.id)
    repo_id_str = params.get("repo_id")

    import uuid as _uuid

    rid = _uuid.UUID(repo_id_str) if repo_id_str else None
    ds = await ds_repo.get_effective(repo_id=rid)

    if not ds:
        return {
            "found": False,
            "content": "",
            "message": "No design system extracted for this repository or organization.",
        }

    logger.info(
        "mcp_get_design_system",
        org_id=str(org.id),
        repo_id=repo_id_str,
        content_length=len(ds.content or ""),
    )
    return {
        "found": True,
        "repo_id": str(ds.repo_id) if ds.repo_id else None,
        "is_default": ds.is_default,
        "content": ds.content or "",
    }


TOOL_HANDLERS: dict[str, Any] = {
    "get_bud_context": handle_get_bud_context,
    "write_bud": handle_write_bud,
    "get_knowledge": handle_get_knowledge,
    "search_bugs": handle_search_bugs,
    "update_task_status": handle_update_task_status,
    "post_slack_message": handle_post_slack_message,
    "get_team_context": handle_get_team_context,
    "get_pending_features": handle_get_pending_features,
    "write_feature_registry": handle_write_feature_registry,
    "check_feature_exists": handle_check_feature_exists,
    "list_design_systems": handle_list_design_systems,
    "get_design_system": handle_get_design_system,
}
