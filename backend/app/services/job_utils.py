"""Shared utilities for async job handlers.

Contains the common Claude runner invocation pattern, MCP config builder,
progress callbacks, and other helpers used across job_chat, job_design,
and job_agents modules.
"""

import asyncio
import base64
import os
import tempfile
import uuid as uuid_mod
from pathlib import Path
from typing import Any

import structlog

from app.services.claude_runner import ProgressCallback
from app.services.job_queue import update_job

logger = structlog.get_logger(__name__)

# Per-thread lock map for triage serialization
thread_locks: dict[str, asyncio.Lock] = {}

# Per-section lock map for chat serialization.
# Prevents two concurrent chat jobs from reading the same section content,
# producing conflicting edits, and having last-write-wins overwrite the other.
section_locks: dict[str, asyncio.Lock] = {}

# Max characters of chat history to include in LLM prompts
HISTORY_CHAR_BUDGET = 2000


# ── Real-time progress for Claude agent jobs ──────────────────────


def _format_tool_progress(tool_name: str, tool_input: dict[str, Any]) -> str:
    """Format a human-readable progress message from a tool_use event."""
    short = tool_name.split("__")[-1] if "__" in tool_name else tool_name

    # Extract common fields
    file_path = tool_input.get("file_path", "")
    if file_path:
        file_path = file_path.rsplit("/", 1)[-1]  # basename only

    match short:
        # Claude built-in tools — show detail from input
        case "Read":
            return f"Reading {file_path}..." if file_path else "Reading file..."
        case "Write":
            return f"Writing {file_path}..." if file_path else "Writing file..."
        case "Edit":
            return f"Editing {file_path}..." if file_path else "Editing file..."
        case "Glob":
            pattern = tool_input.get("pattern", "")
            return f"Finding {pattern}..." if pattern else "Finding files..."
        case "Grep":
            pattern = tool_input.get("pattern", "")
            return f"Searching for '{pattern[:40]}'..." if pattern else "Searching code..."
        case "Bash":
            cmd = tool_input.get("command", "")
            preview = cmd[:50].split("\n")[0]
            return f"Running: {preview}..." if preview else "Running command..."
        # MCP tools — static messages
        case "get_bud_context":
            return "Reading BUD requirements..."
        case "list_design_systems":
            return "Discovering design systems..."
        case "get_design_system":
            return "Loading design tokens..."
        case "update_task_status":
            return "Updating status..."
        case "check_feature_exists":
            return "Checking features..."
        case "search_bugs":
            return "Searching bugs..."
        case _:
            return f"Using {short}..."


def make_progress_callback(job_id: str) -> ProgressCallback:
    """Create a progress callback that updates a job's status message on each tool call."""

    def _on_tool_use(tool_name: str, tool_input: dict[str, Any]) -> None:
        msg = _format_tool_progress(tool_name, tool_input)
        update_job(job_id, status_message=msg)

    return _on_tool_use


def build_mcp_config(
    org_id: str,
    tool_names: list[str] | None = None,
) -> Any:
    """Build an MCPServerConfig for a Claude CLI run.

    Creates an internal MCP token scoped to the org and returns a config
    that the Claude runner will use to spawn the stdio bridge subprocess.

    Returns None if the MCP backend URL is not configured.
    """
    from app.services.claude_runner import MCPServerConfig

    try:
        from app.config import settings as app_settings
        from app.mcp.auth import create_internal_mcp_token

        if not app_settings.mcp_backend_url:
            return None

        token = create_internal_mcp_token(uuid_mod.UUID(org_id))
        return MCPServerConfig(
            backend_url=app_settings.mcp_backend_url,
            mcp_token=token,
            tool_names=tool_names or [],
        )
    except Exception:
        logger.warning("mcp_config_build_failed", org_id=org_id)
        return None


async def resolve_repo_path(repo_id: str | None, org_id: str) -> str | None:
    """Look up a tracked repository's local path by its UUID.

    Returns the path string or None if not found / no repo_id given.
    """
    if not repo_id:
        return None
    from app.database import AsyncSessionLocal
    from app.models.tracked_repository import TrackedRepository

    try:
        async with AsyncSessionLocal() as db:
            tracked = await db.get(TrackedRepository, uuid_mod.UUID(repo_id))
            if tracked and tracked.org_id == uuid_mod.UUID(org_id):
                return tracked.path
            return None
    except Exception:
        logger.warning("resolve_repo_path_failed", repo_id=repo_id)
        return None


async def record_agent_timeline(
    org_id: str,
    bud_id: str,
    event_type: str,
    *,
    skill_name: str,
    section: str,
    job_id: str,
    extra_detail: dict[str, Any] | None = None,
) -> None:
    """Record an AI agent timeline event in a fresh DB session.

    Job handlers create their own sessions, so this uses AsyncSessionLocal.
    """
    from app.database import AsyncSessionLocal
    from app.services.bud_timeline import record_event

    detail = extra_detail or {
        "agent": skill_name,
        "section": section,
        "job_id": job_id,
    }
    try:
        async with AsyncSessionLocal() as tl_db:
            await record_event(
                tl_db,
                uuid_mod.UUID(org_id),
                uuid_mod.UUID(bud_id),
                event_type,
                detail=detail,
            )
            await tl_db.commit()
    except Exception:
        logger.warning(
            "timeline_event_failed",
            event_type=event_type,
            bud_id=bud_id,
        )


def get_thread_key(event_data: dict[str, Any]) -> str:
    """Extract a unique key for Slack thread serialization."""
    item = event_data.get("item", {})
    channel = item.get("channel", event_data.get("channel", ""))
    ts = item.get("ts", event_data.get("thread_ts", ""))
    return f"{channel}:{ts}"


def save_image_temp(data_url: str, index: int) -> Path | None:
    """Decode a base64 data-URL image and write it to a temp file.

    Args:
        data_url: A ``data:image/...;base64,...`` string.
        index: Image index (for unique naming).

    Returns:
        Path to the written temp file, or None on failure.
    """
    try:
        header, data = data_url.split(",", 1)
        ext = "png"
        if "image/jpeg" in header:
            ext = "jpg"
        elif "image/gif" in header:
            ext = "gif"
        elif "image/webp" in header:
            ext = "webp"

        raw = base64.b64decode(data)
        fd, tmp_path = tempfile.mkstemp(suffix=f".{ext}", prefix=f"chat_image_{index}_")
        os.close(fd)
        path = Path(tmp_path)
        path.write_bytes(raw)
        return path
    except Exception:
        logger.warning("image_save_failed", index=index)
        return None
