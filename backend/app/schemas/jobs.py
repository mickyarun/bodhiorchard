# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Pydantic schemas for the async job queue system."""

import uuid
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class JobState(StrEnum):
    """Possible states for an async job."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


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
    skill_id: str | None = None
    task_id: str | None = None


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
    # Platform slug (see app.services.platforms). The handler resolves this
    # back to a Platform instance to select the correct design-file globs,
    # skip directories, and LLM prompt idiom. Required — there is no sensible
    # cross-platform default and silently classifying a Flutter repo as
    # web_js is exactly the bug this field exists to prevent.
    platform: str


class BulkOnboardItemState(StrEnum):
    """Per-item lifecycle states reported through job progress."""

    PENDING = "pending"
    CLONING = "cloning"
    DONE = "done"
    ERROR = "error"


class BulkOnboardItemProgress(BaseModel):
    """Per-item progress + outcome row carried inside the job payload.

    The same shape is used both as the persistent payload (so the
    handler can look up branches per item) and as the per-item progress
    snapshot the frontend reads via ``useJobSocket``.
    """

    full_name: str = Field(alias="fullName")
    main_branch: str = Field(alias="mainBranch")
    develop_branch: str | None = Field(default=None, alias="developBranch")
    uat_branch: str | None = Field(default=None, alias="uatBranch")
    status: BulkOnboardItemState = BulkOnboardItemState.PENDING
    repo_id: uuid.UUID | None = Field(default=None, alias="repoId")
    error: str | None = None

    model_config = ConfigDict(populate_by_name=True)


class BulkOnboardJobPayload(BaseModel):
    """Payload for the bulk-onboard async job.

    The list of ``items`` is mutated in place by the handler — each
    child coroutine flips its row's ``status`` (and ``repo_id`` /
    ``error`` on terminal states) and the whole list is republished
    through ``update_job(result=...)`` for the websocket client.
    """

    org_id: uuid.UUID = Field(alias="orgId")
    items: list[BulkOnboardItemProgress]

    model_config = ConfigDict(populate_by_name=True)


class BUDAgentTaskPayload(BaseModel):
    """Standardized payload for all BUD agent tasks.

    The handler reads everything else from the DB via the task row
    (which has skill_id, bud_id, org_id). No per-agent payload needed.
    """

    org_id: str
    bud_id: str
    task_id: str
