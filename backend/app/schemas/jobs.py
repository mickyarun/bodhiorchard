"""Pydantic schemas for the async job queue system."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class JobState(StrEnum):
    """Possible states for an async job."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class JobStatusRead(BaseModel):
    """Response schema for job status polling (GET /v1/jobs/{id}/status)."""

    job_id: str = Field(alias="jobId")
    job_type: str = Field(alias="jobType")
    state: JobState
    status_message: str = Field(default="", alias="statusMessage")
    progress_pct: int = Field(default=0, alias="progressPct")
    result: Any = None
    error: str | None = None

    model_config = {"populate_by_name": True}


class JobCreatedResponse(BaseModel):
    """Response schema when a job is created (202 Accepted)."""

    job_id: str = Field(alias="jobId")

    model_config = {"populate_by_name": True}


# ── Typed Payloads (per job type) ──────────────────────────────────


class ChatJobPayload(BaseModel):
    """Payload for BUD chat jobs. Validated before queuing."""

    bud_id: str
    org_id: str
    bud_number: int
    section: str
    current_content: str
    title: str
    message: str
    design_id: str | None = None
    repo_id: str | None = None
    user_id: str | None = None
    session_id: str | None = None
    images: list[str] = Field(default_factory=list)


class TriageJobPayload(BaseModel):
    """Payload for Slack triage jobs."""

    team_id: str
    action: str  # "start_triage" | "continue_triage" | "pm_approval"
    event_type: str
    event_data: dict[str, Any]
    approved: bool | None = None


class PRDAgentJobPayload(BaseModel):
    """Payload for PRD agent enrichment jobs."""

    org_id: str
    bud_id: str
    bud_number: int
    session_id: str
    bot_token_encrypted: str
    slack_channel: str
    thread_ts: str


class DesignAgentJobPayload(BaseModel):
    """Payload for auto-generating initial design wireframe on phase transition."""

    org_id: str
    bud_id: str
    bud_number: int
    title: str
    requirements_md: str
    repo_id: str | None = None
    design_id: str | None = None


class TechArchJobPayload(BaseModel):
    """Payload for tech architecture generation jobs."""

    org_id: str
    bud_id: str
    bud_number: int
    title: str
    requirements_md: str


class CodeReviewJobPayload(BaseModel):
    """Payload for automated code review + test plan generation."""

    org_id: str
    bud_id: str
    bud_number: int
    title: str
    tech_spec_md: str
    confirmed_repos: list[dict[str, str]] = Field(default_factory=list)


class DesignExtractJobPayload(BaseModel):
    """Payload for design system extraction jobs."""

    org_id: str
    repo_id: str
    repo_path: str
    is_default: bool = False


class BUDAgentTaskPayload(BaseModel):
    """Standardized payload for all BUD agent tasks.

    The handler reads everything else from the DB via the task row
    (which has skill_id, bud_id, org_id). No per-agent payload needed.
    """

    org_id: str
    bud_id: str
    task_id: str
