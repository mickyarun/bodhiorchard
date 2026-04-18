"""Pydantic schemas for agent activity tracking."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class AgentActivityHookRequest(BaseModel):
    """Request body for agent activity reports.

    Sent by hook scripts (when BODHIORCHARD_AGENT_SKILL_SLUG is set)
    to POST /mcp/agent-activity, or by backend directly for
    skill lifecycle events.
    """

    session_id: str = Field(default="", max_length=100)
    event_type: Literal[
        "session_start",
        "session_end",
        "activity_summary",
        "commit",
        "file_change",
        "tool_call",
        "tool_error",
        "api_error",
        "user_prompt",
        "subagent_start",
        "subagent_stop",
        "skill_invoked",
        "skill_completed",
        "skill_failed",
    ]
    skill_slug: str = Field(default="", max_length=100)
    agent_type: str = Field(default="", max_length=100)
    agent_task_id: str = Field(default="", max_length=100)
    bud_number: int | None = None
    author_email: str = Field(default="", max_length=255)
    branch: str = Field(default="", max_length=500)
    repo_path: str = Field(default="", max_length=1000)
    message: str = Field(default="", max_length=2000)
    commit_sha: str = Field(default="", max_length=40)
    file_path: str = Field(default="", max_length=1000)
    files_changed: str = Field(default="", max_length=5000)
    metadata: dict | None = None


class AgentActivityHookResponse(BaseModel):
    """Response for agent activity reports."""

    success: bool
    event_type: str
    bud_number: int | None = None
    user_resolved: bool = False
    skill_resolved: bool = False
    error: str | None = None


class AgentActivityRead(BaseModel):
    """Schema for reading a single agent activity entry."""

    id: uuid.UUID
    event_type: str
    status: str | None = None
    message: str | None = None
    source: str
    skill_slug: str | None = None
    agent_type: str | None = None
    actor_name: str | None = None
    session_id: str | None = None
    branch: str | None = None
    commit_sha: str | None = None
    file_path: str | None = None
    metadata: dict | None = Field(None, validation_alias="metadata_")
    created_at: datetime

    model_config = {"from_attributes": True}
