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

"""Pydantic schemas for BUD CRUD endpoints.

Section + stage constants (``BUD_SECTIONS``, ``SECTION_REQUIRED_STAGES``,
``BUD_AGENT_SECTIONS``, etc.) live in :mod:`app.schemas.bud_constants`.
This module hosts only the request/response DTO classes.
"""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.models.bud import BUDStatus

# Re-export design schemas so legacy imports keep working; new code
# should import directly from :mod:`app.schemas.bud_design`.
from app.schemas.bud_design import (  # noqa: F401
    BUDDesignRead,
    DesignGenerateRequest,
    DesignHtmlUpdate,
)


class BUDCreate(BaseModel):
    """Schema for creating a new BUD."""

    title: str = Field(..., min_length=1, max_length=500)
    requirements_md: str | None = None
    metadata_: dict[str, Any] | None = Field(None, alias="metadata")
    # Optional "Advanced settings" picks: map each BUD stage to a specific
    # AgentSkill id. Stages omitted (or the whole field omitted) fall back
    # to the org's default skill for that stage's agent type. Validated in
    # the route handler against the caller's org.
    stage_skill_overrides: dict[BUDStatus, uuid.UUID] | None = None
    # Per-phase auto-generation. Keys: "bud" / "design" / "tech_arch" /
    # "testing". Value true = our agent fires; false / missing = skip.
    # DEFAULT EMPTY DICT = all phases skip. User opts in per phase via
    # the Advanced-settings switches; for everything they leave off the
    # local-AI / external-LLM flow takes over.
    auto_generate_phases: dict[str, bool] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}


class BUDUpdate(BaseModel):
    """Schema for updating an existing BUD."""

    title: str | None = Field(None, min_length=1, max_length=500)
    status: str | None = None
    status_override_reason: str | None = Field(None, max_length=2000)
    requirements_md: str | None = None
    tech_spec_md: str | None = None
    test_plan_md: str | None = None
    code_review_comments: list[dict[str, Any]] | None = None
    metadata_: dict[str, Any] | None = Field(None, alias="metadata")
    assignee_id: uuid.UUID | None = None
    # Per-phase auto-generate map can be flipped post-creation from the
    # BUD detail page. Send the FULL desired map; the backend replaces
    # the column verbatim. Send {} to clear (= all phases skip).
    auto_generate_phases: dict[str, bool] | None = None

    model_config = {"populate_by_name": True}


class BUDAgentTaskRead(BaseModel):
    """Schema for reading a BUD agent task."""

    id: uuid.UUID
    task_type: str
    skill_slug: str = ""
    status: str
    job_id: str | None = None
    attempt: int = 1
    status_message: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @model_validator(mode="before")
    @classmethod
    def extract_skill_slug(cls, data: Any) -> Any:
        """Pull skill_slug from the joined AgentSkill relationship."""
        if hasattr(data, "skill") and data.skill is not None:
            data.skill_slug = data.skill.skill_slug
        return data


class BUDRead(BaseModel):
    """Schema for reading a single BUD with full content."""

    id: uuid.UUID
    org_id: uuid.UUID
    bud_number: int
    title: str
    status: str
    requirements_md: str | None = None
    tech_spec_md: str | None = None
    test_plan_md: str | None = None
    qa_automation_cases: list[dict[str, Any]] | None = None
    qa_manual_cases: list[dict[str, Any]] | None = None
    qa_execution_plan_md: str | None = None
    code_review_comments: list[dict[str, Any]] | None = None
    # Empty dict / None means "all phases skip" — the new default for
    # newly created BUDs. Returned to the frontend so the BUD detail
    # banner can decide which phases are user-driven.
    auto_generate_phases: dict[str, bool] | None = None
    designs: list[BUDDesignRead] = []
    metadata: dict[str, Any] | None = Field(None, validation_alias="metadata_")
    impacted_repos: list[dict[str, Any]] | None = None
    estimated_dates: dict[str, Any] | None = None
    complexity: int | None = None
    prod_p70_date: datetime | None = None
    current_phase_deadline: datetime | None = None
    assignee_id: uuid.UUID | None = None
    assignee_name: str | None = None
    active_agent_task: BUDAgentTaskRead | None = None
    # In-flight phase-worker event (assignment / todo-gen / estimation):
    # see services/agent_activity_logger.py. ``None`` when nothing is running.
    active_phase_worker: dict[str, str] | None = None
    # Sticky last-failed-phase banner sourced from agent_activity_logs newer
    # than ``phase_failure_acknowledged_at``; cleared via the dismiss endpoint.
    last_phase_failure: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True, "populate_by_name": True}

    @model_validator(mode="before")
    @classmethod
    def extract_assignee_name(cls, data: Any) -> Any:
        """Pull assignee name from the joined User relationship."""
        if hasattr(data, "assignee") and data.assignee is not None:
            data.assignee_name = data.assignee.name
        return data


class BUDListItem(BaseModel):
    """Schema for BUD list view (no full content)."""

    id: uuid.UUID
    bud_number: int
    title: str
    status: str
    complexity: int | None = None
    prod_p70_date: datetime | None = None
    current_phase_deadline: datetime | None = None
    assignee_id: uuid.UUID | None = None
    assignee_name: str | None = None
    open_bug_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @model_validator(mode="before")
    @classmethod
    def extract_assignee_name(cls, data: Any) -> Any:
        """Pull assignee name from the joined User relationship."""
        if hasattr(data, "assignee") and data.assignee is not None:
            data.assignee_name = data.assignee.name
        return data


class ChatMessageRead(BaseModel):
    """Schema for a persisted chat message."""

    id: uuid.UUID
    role: str
    message: str
    user_id: uuid.UUID | None = None
    session_id: uuid.UUID | None = None
    user_name: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class RejectTechArchRequest(BaseModel):
    """Schema for rejecting a tech architecture plan."""

    reason: str = Field(..., min_length=1, max_length=5000)


class ReassignmentRequest(BaseModel):
    """Schema for requesting developer reassignment."""

    reason: str = Field(..., min_length=1, max_length=5000)


class TimelineEventRead(BaseModel):
    """Schema for reading a BUD timeline event."""

    id: uuid.UUID
    event_type: str
    actor_name: str | None = None
    detail: dict[str, Any] | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
