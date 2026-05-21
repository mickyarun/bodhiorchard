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

"""MCP (Model Context Protocol) server for Bodhiorchard.

Exposes tools that Claude Code can call to read/write Bodhiorchard data:
BUDs, features, bugs, task status, team context.

Mounted at /mcp/ on the main FastAPI app.
"""

from typing import Any, cast

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.mcp.audit import emit_audit
from app.mcp.auth import MCPAuthResult, verify_mcp_token
from app.mcp.handlers_agent_activity import handle_agent_activity
from app.mcp.handlers_bud import (
    handle_get_bud_context,
    handle_write_bud,
)
from app.mcp.handlers_bud_design import (
    handle_get_bud_designs,
    handle_write_bud_design,
)
from app.mcp.handlers_bud_writes import (
    handle_create_bud,
    handle_get_bud_by_id,
    handle_update_bud,
)
from app.mcp.handlers_code_graph import (
    handle_code_community,
    handle_code_context,
    handle_code_god_nodes,
    handle_code_impact,
    handle_code_query,
    handle_code_stats,
)
from app.mcp.handlers_features import (
    handle_check_feature_exists,
    handle_get_features,
    handle_get_pending_features,
    handle_search_bugs,
    handle_write_feature_registry,
)
from app.mcp.handlers_hooks import handle_dev_activity
from app.mcp.handlers_prompts import CANONICAL_TASK_TYPES, handle_get_prompt
from app.mcp.handlers_scan import handle_write_synthesis_feature
from app.mcp.handlers_team import (
    handle_get_design_system,
    handle_get_team_context,
    handle_list_design_systems,
    handle_post_slack_message,
)
from app.mcp.handlers_todo import (
    handle_complete_todo,
    handle_get_bud_plan,
    handle_takeover_todo,
)
from app.mcp.rate_limit import enforce_rate_limit
from app.mcp.synthesis_queue import (  # noqa: F401
    clear_synthesis_queue,
    get_queue_remaining,
    remove_from_queue,
    set_synthesis_queue,
)
from app.schemas.agent_activity import (
    AgentActivityHookRequest,
    AgentActivityHookResponse,
)
from app.schemas.dev_activity import DevActivityHookRequest, DevActivityHookResponse

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
        description=(
            "Retrieve EXISTING IN-PROGRESS BUDs (anything not closed or "
            "discarded) for context when drafting a new one. Optional "
            "``query`` does substring keyword search on title + "
            "requirements_md (same tokenisation as get_features). Pass "
            "include_terminal=true to also see closed/discarded history."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Max BUDs to return (default 5, max 20)",
                    "default": 5,
                },
                "query": {
                    "type": "string",
                    "description": (
                        "Optional keyword filter — whitespace-tokenised "
                        "substring match on title + requirements_md. "
                        "Tokens shorter than 2 chars are dropped. Omit "
                        "to get the most recent BUDs."
                    ),
                },
                "include_terminal": {
                    "type": "boolean",
                    "description": (
                        "Include closed and discarded BUDs in the result. "
                        "Default false — those are usually noise for the "
                        "BYO-AI drafting flow."
                    ),
                    "default": False,
                },
            },
        },
    ),
    MCPToolDefinition(
        name="create_bud",
        description=(
            "Create a new BUD owned by the calling user. Sets you as both "
            "creator and assignee — required so subsequent update_bud calls "
            "from your MCP token can find this BUD. Available remotely as "
            "the write-side of the BYO-AI flow."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "requirements_md": {
                    "type": "string",
                    "description": (
                        "Full markdown body — problem, proposed solution, "
                        "acceptance criteria, edge cases, dependencies."
                    ),
                },
            },
            "required": ["title", "requirements_md"],
        },
    ),
    MCPToolDefinition(
        name="update_bud",
        description=(
            "Update content for the BUD's CURRENT creative phase. The "
            "server picks the target from the phase: requirements_md "
            "when status='bud', the BUD-level wireframe HTML when "
            "'design', or tech_spec_md when 'tech_arch'. Other phases "
            "(testing, code_review, …) are NOT writable via MCP — those "
            "involve PR state, evidence uploads, and stage gates that "
            "stay UI/agent-driven. Only allowed when you are the BUD's "
            "assignee and it isn't closed or discarded."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "bud_id": {"type": "string", "description": "BUD UUID."},
                "content": {
                    "type": "string",
                    "description": (
                        "New content for whichever field the BUD's current "
                        "phase owns. Empty strings are rejected."
                    ),
                },
            },
            "required": ["bud_id", "content"],
        },
    ),
    MCPToolDefinition(
        name="get_bud_by_id",
        description=(
            "Fetch a single BUD by UUID with the full content of every "
            "section (truncated per field). Org-scoped — no assignee "
            "restriction on reads."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "bud_id": {"type": "string", "description": "BUD UUID."},
            },
            "required": ["bud_id"],
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
                "requirements_md": {
                    "type": "string",
                    "description": (
                        "Full Markdown body of the BUD — problem statement, "
                        "proposed solution, acceptance criteria, edge cases, "
                        "dependencies. Matches the DB column name."
                    ),
                },
                "bud_number": {
                    "type": "integer",
                    "description": "Existing BUD number to update (omit to create new)",
                },
            },
            "required": ["title", "requirements_md"],
        },
    ),
    MCPToolDefinition(
        name="get_features",
        description=(
            "Hybrid search over your org's active features. Tries an "
            "exact substring match on title first (same as the frontend "
            "/features ?q=… page); falls back to semantic similarity "
            "over the feature embeddings when the literal phrase isn't "
            "in any title. ALWAYS pass a non-empty ``query`` — an org "
            "with hundreds of features will drown the model in noise "
            "otherwise. Paginate via ``offset`` + ``next_offset`` until "
            "``has_more`` is false. Each result includes ``id`` you can "
            'put into a BUD\'s {"linked_feature_ids": [...]} JSON fence.'
        ),
        input_schema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Keyword or phrase to semantic-search.",
                },
                "limit": {
                    "type": "integer",
                    "default": 10,
                    "description": "Page size (max 50).",
                },
                "offset": {
                    "type": "integer",
                    "default": 0,
                    "description": "Pagination offset; use next_offset from prior page.",
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
            "Stage a synthesised feature for end-of-batch reconciliation. "
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
                "cluster_signature": {
                    "type": "string",
                    "description": (
                        "Stable structural identity (SHA-256 hex of the cluster's"
                        " canonical node-ID list). Looked up from cluster_cache"
                        " by the synthesise stage and echoed back in the prompt"
                        " context — pass it through verbatim."
                    ),
                },
                "head_sha": {
                    "type": "string",
                    "description": (
                        "Optional: current scan's HEAD SHA. Stamped on the row"
                        " as ``last_seen_sha`` so the audit can tell stale rows"
                        " apart. Omit if not surfaced in the prompt."
                    ),
                },
                "source_ref": {
                    "type": "string",
                    "description": (
                        "Optional free-form provenance reference (e.g. PR"
                        " number, BUD-XXX, commit SHA) for traceability."
                    ),
                },
                "repo_name": {
                    "type": "string",
                    "description": "Repository name (links feature to tracked repo)",
                },
            },
            "required": [
                "feature_name",
                "description",
                "capabilities",
                "code_locations",
                "tags",
                "cluster_signature",
                "repo_name",
            ],
        },
    ),
    MCPToolDefinition(
        name="write_synthesis_feature",
        description=(
            "scan pipeline: persist a feature with full meta-community "
            "linkage. Pass the community_id values you received in the "
            "synthesis prompt — both the ones merged into this feature "
            "(``source_community_ids``) and the ones you decided to skip "
            "(``dropped_community_ids``). Backend writes the feature row, "
            "links to source communities, and updates per-community "
            "processing_status. Always pass ``scan_id`` and ``repo_id`` "
            "from the prompt's *Scan context* block — they bind the "
            "feature to this exact scan run."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Human-readable feature name, e.g. 'Card Payments'",
                },
                "description": {
                    "type": "string",
                    "description": "1-2 sentence business description of the feature",
                },
                "source_community_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "community_id values from the synthesis prompt that "
                        "were merged into this feature. Must be non-empty."
                    ),
                },
                "dropped_community_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "community_id values from the synthesis prompt that "
                        "you decided to skip (utility/noise). Optional."
                    ),
                },
                "capabilities": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "3-6 specific things this feature does",
                },
                "code_locations": {
                    "type": "object",
                    "description": (
                        "Map of layer → file paths, e.g. {backend: [...], frontend: [...]}"
                    ),
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "2-5 lowercase search keywords",
                },
                "repo_name": {
                    "type": "string",
                    "description": "Repository name (must be tracked)",
                },
                "scan_id": {
                    "type": "string",
                    "description": (
                        "UUID of the active scan, copied verbatim from the "
                        "prompt's *Scan context* block. Binds this feature "
                        "to the exact scan run. Required during scans; "
                        "omit only for legacy ad-hoc calls."
                    ),
                },
                "repo_id": {
                    "type": "string",
                    "description": (
                        "UUID of the tracked repo, copied verbatim from the "
                        "prompt's *Scan context* block. Used in preference "
                        "to ``repo_name`` lookup when supplied."
                    ),
                },
            },
            "required": [
                "name",
                "description",
                "source_community_ids",
                "repo_name",
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
                "repo_id": {
                    "type": "string",
                    "description": (
                        "Optional repo UUID to scope team context to. Omit for org-wide view."
                    ),
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
    MCPToolDefinition(
        name="get_prompt",
        description=(
            "Return the exact prompt our PM / Designer / TechPlanner / "
            "Tester agent would use for a given BUD stage. Honours the "
            "org's default skill override. Feed this prompt to your local "
            "AI to produce PRD / design / tech-spec / test-plan content "
            "that matches the shape the BUD section editors expect."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "task_type": {
                    "type": "string",
                    # Advertise the canonical role-based names only —
                    # the handler also accepts the internal BUDStatus
                    # aliases (``bud`` for ``pm``, ``tech_arch`` for
                    # ``tech_plan``) for backward compat, but those
                    # don't need to be discoverable here.
                    "enum": list(CANONICAL_TASK_TYPES),
                    "description": (
                        "Which stage's prompt to return: 'pm' (PRD), "
                        "'design', 'tech_plan', or 'testing'."
                    ),
                },
            },
            "required": ["task_type"],
        },
    ),
    MCPToolDefinition(
        name="get_bud_designs",
        description=(
            "Fetch wireframe(s) attached to a BUD, one row per impacted "
            "repo. Call this BEFORE iterating on a design — never assume "
            "the prior wireframe content from your own context. By "
            "default only ``status='ready'`` rows are returned; the "
            "response reports a ``skipped_count`` for any non-ready rows "
            "(still generating or failed) so you can flag the gap in "
            "your output instead of reasoning over empty HTML."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "bud_id": {
                    "type": "string",
                    "description": "BUD UUID to fetch designs for.",
                },
                "repo_id": {
                    "type": "string",
                    "description": (
                        "Optional repo UUID to filter to a single design. "
                        "Omit to get every per-repo design for the BUD. "
                        "When supplied, the row is returned regardless "
                        "of status (designer iteration reads its own "
                        "in-flight row this way)."
                    ),
                },
                "include_non_ready": {
                    "type": "boolean",
                    "description": (
                        "When true (and no repo_id is supplied), return "
                        "rows in every status — useful for debugging or "
                        "tooling that needs to see in-flight state. "
                        "Defaults to false: only ready rows."
                    ),
                },
            },
            "required": ["bud_id"],
        },
    ),
    MCPToolDefinition(
        name="write_bud_design",
        description=(
            "Persist an iterated wireframe HTML back to the BUD's design "
            "row. The HTML is sanitized server-side; the row is upserted "
            "by (bud_id, repo_id) and marked READY. Call this as the "
            "FINAL step of any design iteration — do NOT rely on stdout "
            "JSON parsing for persistence."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "bud_id": {
                    "type": "string",
                    "description": "BUD UUID to attach the wireframe to.",
                },
                "repo_id": {
                    "type": "string",
                    "description": (
                        "Optional repo UUID. Omit for a BUD-level design "
                        "not scoped to any single repository."
                    ),
                },
                "html": {
                    "type": "string",
                    "description": "Complete, self-contained wireframe HTML.",
                },
                "notes": {
                    "type": "string",
                    "description": (
                        "Optional override notes (free text) that take "
                        "priority over the HTML when downstream agents read."
                    ),
                },
            },
            "required": ["bud_id", "html"],
        },
    ),
    MCPToolDefinition(
        name="get_bud_plan",
        description=(
            "Get the implementation plan for a BUD with your assigned TODOs. "
            "Call this when starting work on a bud-NNN/ branch. Returns TODO "
            "titles and which are yours vs assigned to others. The per-TODO "
            "context_md is intentionally NOT included — call takeover_todo "
            "to claim a TODO and receive its implementation details."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "bud_number": {
                    "type": "integer",
                    "description": "BUD number (detect from branch bud-NNN/).",
                },
            },
            "required": ["bud_number"],
        },
    ),
    MCPToolDefinition(
        name="takeover_todo",
        description=(
            "Claim a pending TODO and move it to in_progress. MUST be called "
            "before implementing any TODO. On success returns the full "
            "context_md. On failure (already in_progress/completed or not "
            "yours) returns an explanatory error — skip and try another."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "bud_number": {"type": "integer"},
                "sequence": {
                    "type": "integer",
                    "description": "The TODO sequence number from get_bud_plan.",
                },
            },
            "required": ["bud_number", "sequence"],
        },
    ),
    MCPToolDefinition(
        name="complete_todo",
        description=(
            "Mark an in_progress TODO as completed with a short summary of "
            "what was implemented. Only the current assignee can complete "
            "a TODO. The summary is shown to other developers via get_bud_plan."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "bud_number": {"type": "integer"},
                "sequence": {"type": "integer"},
                "summary": {
                    "type": "string",
                    "description": (
                        "Brief description of what was implemented "
                        "(e.g., 'Added preferences JSONB column and migration')."
                    ),
                },
            },
            "required": ["bud_number", "sequence", "summary"],
        },
    ),
    MCPToolDefinition(
        name="code_impact",
        description=(
            "Return upstream callers / downstream callees of a target symbol "
            "up to N hops, using the cached call graph from the latest scan. "
            "Use BEFORE editing any function/method/class to assess blast radius."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "target": {
                    "type": "string",
                    "description": "Symbol label or node id (case-insensitive).",
                },
                "repo_id": {
                    "type": "string",
                    "description": "Tracked repo UUID.",
                },
                "direction": {
                    "type": "string",
                    "enum": ["upstream", "downstream", "both"],
                    "default": "upstream",
                },
                "depth": {
                    "type": "integer",
                    "default": 2,
                    "description": "BFS hop limit (max 5).",
                },
            },
            "required": ["target", "repo_id"],
        },
    ),
    MCPToolDefinition(
        name="code_query",
        description=(
            "Substring-rank search across all symbol labels and source files "
            "in the cached call graph. Use to find candidate symbols by name "
            "before calling code_impact / code_context."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "repo_id": {"type": "string"},
                "limit": {"type": "integer", "default": 10},
            },
            "required": ["query", "repo_id"],
        },
    ),
    MCPToolDefinition(
        name="code_context",
        description=(
            "Single-symbol 360°: attributes, callers, and callees from the cached call graph."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "repo_id": {"type": "string"},
            },
            "required": ["symbol", "repo_id"],
        },
    ),
    MCPToolDefinition(
        name="code_community",
        description=(
            "Return cluster metadata + the file and symbol lists for a given "
            "cluster_id (e.g. 'c0'). Lists every file the cluster touches."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "cluster_id": {"type": "string"},
                "repo_id": {"type": "string"},
            },
            "required": ["cluster_id", "repo_id"],
        },
    ),
    MCPToolDefinition(
        name="code_god_nodes",
        description=(
            "Top-N highest-degree nodes in the call graph — likely god classes "
            "or hub functions. Use to spot refactoring candidates."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "repo_id": {"type": "string"},
                "limit": {"type": "integer", "default": 20},
            },
            "required": ["repo_id"],
        },
    ),
    MCPToolDefinition(
        name="code_stats",
        description=(
            "Overall stats for the cached call graph: node/edge counts, "
            "language extension distribution, current head_sha."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "repo_id": {"type": "string"},
            },
            "required": ["repo_id"],
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
    request: Request,
    db: AsyncSession = Depends(get_db),
    auth: MCPAuthResult = Depends(verify_mcp_token),
) -> dict[str, Any]:
    """Execute an MCP tool call from Claude Code.

    Every call is rate-limited (per token, per IP) and recorded in the
    ``mcp_audit_log`` table for incident response. Both checks are
    transport-level cross-cutting concerns — neither knows or cares which
    specific handler ends up running.

    Args:
        tool_name: The name of the tool to execute.
        body: Tool call parameters.
        request: FastAPI request, used to derive client IP / user-agent.
        db: The async database session.
        auth: The authenticated org (and optional user) from MCP token.

    Returns:
        Tool execution result.
    """
    logger.info(
        "mcp_tool_call",
        tool=tool_name,
        org_id=str(auth.org.id),
        user_id=str(auth.user.id) if auth.user else None,
        params=body.params,
    )

    # Rate limit BEFORE dispatch so a spammed unknown tool also gets
    # throttled (otherwise the 404 path is free-to-spam).
    try:
        await enforce_rate_limit(request=request, auth=auth, tool_name=tool_name)
    except HTTPException as exc:
        emit_audit(
            request=request,
            auth=auth,
            org_id=auth.org.id,
            token_id=auth.token_id,
            tool_name=tool_name,
            transport="http",
            params=body.params,
            status_code=exc.status_code,
        )
        raise

    # Auth-aware handlers receive the full MCPAuthResult (needs user).
    auth_handler = AUTH_TOOL_HANDLERS.get(tool_name)
    handler = TOOL_HANDLERS.get(tool_name)
    if auth_handler is None and handler is None:
        emit_audit(
            request=request,
            auth=auth,
            org_id=auth.org.id,
            token_id=auth.token_id,
            tool_name=tool_name,
            transport="http",
            params=body.params,
            status_code=status.HTTP_404_NOT_FOUND,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown tool: {tool_name}",
        )

    try:
        if auth_handler is not None:
            result = cast(dict[str, Any], await auth_handler(db, auth, body.params))
        else:
            assert handler is not None  # checked above
            result = cast(dict[str, Any], await handler(db, auth.org, body.params))
    except HTTPException as exc:
        emit_audit(
            request=request,
            auth=auth,
            org_id=auth.org.id,
            token_id=auth.token_id,
            tool_name=tool_name,
            transport="http",
            params=body.params,
            status_code=exc.status_code,
        )
        raise
    except Exception:
        emit_audit(
            request=request,
            auth=auth,
            org_id=auth.org.id,
            token_id=auth.token_id,
            tool_name=tool_name,
            transport="http",
            params=body.params,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
        raise

    emit_audit(
        request=request,
        auth=auth,
        org_id=auth.org.id,
        token_id=auth.token_id,
        tool_name=tool_name,
        transport="http",
        status_code=status.HTTP_200_OK,
    )
    return result


# --- Tool handler dispatch ---

# Handlers that only need the org. Signature: ``(db, org, params)``.
TOOL_HANDLERS: dict[str, Any] = {
    "get_bud_context": handle_get_bud_context,
    "write_bud": handle_write_bud,
    "get_features": handle_get_features,
    "search_bugs": handle_search_bugs,
    "post_slack_message": handle_post_slack_message,
    "get_team_context": handle_get_team_context,
    "get_pending_features": handle_get_pending_features,
    "write_feature_registry": handle_write_feature_registry,
    "write_synthesis_feature": handle_write_synthesis_feature,
    "check_feature_exists": handle_check_feature_exists,
    "list_design_systems": handle_list_design_systems,
    "get_design_system": handle_get_design_system,
    "get_prompt": handle_get_prompt,
    "get_bud_designs": handle_get_bud_designs,
    "write_bud_design": handle_write_bud_design,
    "code_impact": handle_code_impact,
    "code_query": handle_code_query,
    "code_context": handle_code_context,
    "code_community": handle_code_community,
    "code_god_nodes": handle_code_god_nodes,
    "code_stats": handle_code_stats,
}

# Handlers that need the authenticated user (per-user MCP token).
# Signature: ``(db, auth, params)``.
AUTH_TOOL_HANDLERS: dict[str, Any] = {
    "get_bud_plan": handle_get_bud_plan,
    "takeover_todo": handle_takeover_todo,
    "complete_todo": handle_complete_todo,
    "create_bud": handle_create_bud,
    "update_bud": handle_update_bud,
    "get_bud_by_id": handle_get_bud_by_id,
}


# ── Claude Code Hook Endpoint ─────────────────────────────────────


@router.post("/dev-activity", response_model=DevActivityHookResponse)
async def report_dev_activity(
    request: Request,
    db: AsyncSession = Depends(get_db),
    auth: MCPAuthResult = Depends(verify_mcp_token),
) -> DevActivityHookResponse:
    """Receive developer activity reports from Claude Code hooks.

    Authenticated via MCP token (Bearer header). Per-user tokens
    resolve both the org and the specific developer directly.

    Called by hook scripts: session-start.sh, post-commit-track.sh,
    activity-report.sh. All calls are fire-and-forget from the hook side.
    """
    raw = await request.body()
    logger.info("dev_activity_raw_body", body=raw.decode("utf-8", errors="replace")[:2000])
    try:
        body = DevActivityHookRequest.model_validate_json(raw)
    except Exception:
        raw_str = raw.decode("utf-8", errors="replace")[:500]
        logger.error("dev_activity_validation_failed", body=raw_str)
        raise
    return await handle_dev_activity(db, auth, body)


@router.post("/agent-activity", response_model=AgentActivityHookResponse)
async def report_agent_activity(
    request: Request,
    db: AsyncSession = Depends(get_db),
    auth: MCPAuthResult = Depends(verify_mcp_token),
) -> AgentActivityHookResponse:
    """Receive agent activity reports from hooks and backend.

    Called by hook scripts in tracked repos when BODHIORCHARD_AGENT_SKILL_SLUG
    env var is set (agent session), and by backend directly for skill
    lifecycle events. All calls are fire-and-forget from the hook side.
    """
    raw = await request.body()
    logger.info("agent_activity_raw_body", body=raw.decode("utf-8", errors="replace")[:2000])
    try:
        body = AgentActivityHookRequest.model_validate_json(raw)
    except Exception:
        raw_str = raw.decode("utf-8", errors="replace")[:500]
        logger.error("agent_activity_validation_failed", body=raw_str)
        raise
    return await handle_agent_activity(db, auth, body)
