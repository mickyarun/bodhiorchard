"""MCP (Model Context Protocol) server for FlowDev.

Exposes tools that Claude Code can call to read/write FlowDev data:
PRDs, knowledge base, bugs, task status, team context.

Mounted at /mcp/ on the main FastAPI app.
"""

from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.mcp.auth import verify_mcp_token
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
        name="get_prd_context",
        description="Retrieve existing PRDs for context when generating new ones",
        input_schema={
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "Project ID to fetch PRDs for"},
                "limit": {"type": "integer", "description": "Max PRDs to return", "default": 5},
            },
        },
    ),
    MCPToolDefinition(
        name="write_prd",
        description="Save a generated PRD document to the FlowDev database",
        input_schema={
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "content": {"type": "string"},
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
            },
            "required": ["query"],
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
        description="Report task progress back to FlowDev",
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


async def handle_get_prd_context(
    db: AsyncSession,
    org: Organization,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Retrieve existing PRDs for context."""
    # TODO: Query prd_documents table with org_id filter
    logger.info("mcp_get_prd_context", org_id=str(org.id), params=params)
    return {"prds": [], "message": "PRD retrieval not yet implemented"}


async def handle_write_prd(
    db: AsyncSession,
    org: Organization,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Save a generated PRD to the database."""
    title = params.get("title", "")
    # TODO: Insert into prd_documents table (content = params["content"])
    logger.info("mcp_write_prd", org_id=str(org.id), title=title)
    return {"success": True, "message": f"PRD '{title}' saved (stub)"}


async def handle_get_knowledge(
    db: AsyncSession,
    org: Organization,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Query knowledge base via semantic search (pgvector)."""
    query = params.get("query", "")
    # TODO: Embed query and search knowledge_items with pgvector (limit = params["limit"])
    logger.info("mcp_get_knowledge", org_id=str(org.id), query=query[:100])
    return {"results": [], "message": "Knowledge search not yet implemented"}


async def handle_search_bugs(
    db: AsyncSession,
    org: Organization,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Search bugs by description."""
    query = params.get("query", "")
    # TODO: Query bugs table with text search (status = params["status"])
    logger.info("mcp_search_bugs", org_id=str(org.id), query=query[:100])
    return {"bugs": [], "message": "Bug search not yet implemented"}


async def handle_update_task_status(
    db: AsyncSession,
    org: Organization,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Update task/agent log status."""
    task_id = params.get("task_id", "")
    task_status = params.get("status", "")
    # TODO: Update agent_logs table (message = params["message"])
    logger.info(
        "mcp_update_task_status",
        org_id=str(org.id),
        task_id=task_id,
        status=task_status,
    )
    return {"success": True, "message": f"Task {task_id} updated to {task_status} (stub)"}


async def handle_post_slack_message(
    db: AsyncSession,
    org: Organization,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Post message to Slack via stored bot token."""
    channel = params.get("channel", "")
    # TODO: Look up Slack bot token for org, call Slack API (message = params["message"])
    logger.info("mcp_post_slack", org_id=str(org.id), channel=channel)
    return {"success": True, "message": f"Slack message to {channel} (stub)"}


async def handle_get_team_context(
    db: AsyncSession,
    org: Organization,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Read team capacity and active work."""
    # TODO: Query users and skill_profiles tables
    logger.info("mcp_get_team_context", org_id=str(org.id))
    return {"team": [], "message": "Team context not yet implemented"}


TOOL_HANDLERS: dict[str, Any] = {
    "get_prd_context": handle_get_prd_context,
    "write_prd": handle_write_prd,
    "get_knowledge": handle_get_knowledge,
    "search_bugs": handle_search_bugs,
    "update_task_status": handle_update_task_status,
    "post_slack_message": handle_post_slack_message,
    "get_team_context": handle_get_team_context,
}
