"""MCP (Model Context Protocol) server for Bodhigrove.

Exposes tools that Claude Code can call to read/write Bodhigrove data:
BUDs, knowledge base, bugs, task status, team context.

Mounted at /mcp/ on the main FastAPI app.
"""

from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.mcp.auth import verify_mcp_token
from app.mcp.handlers_bud import (
    handle_get_bud_context,
    handle_update_task_status,
    handle_write_bud,
)
from app.mcp.handlers_knowledge import (
    handle_check_feature_exists,
    handle_get_knowledge,
    handle_get_pending_features,
    handle_merge_features,
    handle_search_bugs,
    handle_write_feature_registry,
)
from app.mcp.handlers_team import (
    handle_get_design_system,
    handle_get_team_context,
    handle_list_design_systems,
    handle_post_slack_message,
)
from app.mcp.synthesis_queue import (  # noqa: F401
    clear_synthesis_queue,
    get_queue_remaining,
    remove_from_queue,
    set_synthesis_queue,
)
from app.models.organization import Organization

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/mcp", tags=["mcp"])


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
        name="merge_features",
        description=(
            "Merge duplicate features across repos. Keeps the feature with "
            "keep_title, deactivates features in merge_titles, and links the "
            "kept feature to all specified repos."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "keep_title": {
                    "type": "string",
                    "description": (
                        "Title of the feature to keep "
                        "(e.g. 'Feature: Authentication')"
                    ),
                },
                "merge_titles": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Titles of duplicate features to merge into the kept "
                        "one (will be deactivated)"
                    ),
                },
                "repo_names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "All repo names this merged feature belongs to"
                    ),
                },
            },
            "required": ["keep_title", "repo_names"],
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


# --- Route handlers ---


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


# --- Tool handler dispatch ---

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
    "merge_features": handle_merge_features,
    "list_design_systems": handle_list_design_systems,
    "get_design_system": handle_get_design_system,
}
