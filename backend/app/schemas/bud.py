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

"""Pydantic schemas for BUD CRUD endpoints."""

import uuid
from datetime import datetime
from typing import Any, NamedTuple

from pydantic import BaseModel, Field, model_validator


class BUDSectionInfo(NamedTuple):
    """Metadata for a single BUD section."""

    tab: str
    label: str
    exportable: bool


# Canonical section config: DB field → (tab slug, UI label, exportable?)
# Backend notification service, job handlers, and API validation all derive from this.
# Frontend has a mirror in frontend/src/types/index.ts → BUD_SECTIONS.
BUD_SECTIONS: dict[str, BUDSectionInfo] = {
    "requirements_md": BUDSectionInfo("requirements", "Requirements", True),
    "tech_spec_md": BUDSectionInfo("tech-spec", "Tech Spec", True),
    "test_plan_md": BUDSectionInfo("test-plan", "Test Plan", True),
    "testing": BUDSectionInfo("testing", "Testing", False),
    "design": BUDSectionInfo("design", "Design", False),
}

# Derived helpers
SECTION_TO_TAB: dict[str, str] = {k: v.tab for k, v in BUD_SECTIONS.items()}
TAB_TO_SECTION: dict[str, str] = {v.tab: k for k, v in BUD_SECTIONS.items()}
SECTION_LABELS: dict[str, str] = {k: v.label for k, v in BUD_SECTIONS.items()}
VALID_SECTIONS: set[str] = set(BUD_SECTIONS)
EXPORTABLE_SECTIONS: tuple[str, ...] = tuple(k for k, v in BUD_SECTIONS.items() if v.exportable)
SECTION_PATTERN: str = "^(" + "|".join(BUD_SECTIONS) + ")$"


class BUDCreate(BaseModel):
    """Schema for creating a new BUD."""

    title: str = Field(..., min_length=1, max_length=500)
    requirements_md: str | None = None
    metadata_: dict[str, Any] | None = Field(None, alias="metadata")

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

    model_config = {"populate_by_name": True}


class BUDDesignRead(BaseModel):
    """Schema for reading a BUD design wireframe."""

    id: uuid.UUID
    bud_id: uuid.UUID
    repo_id: uuid.UUID | None = None
    repo_name: str | None = None
    design_html: str | None = None
    notes: str | None = None
    status: str
    job_id: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DesignGenerateRequest(BaseModel):
    """Schema for requesting design generation for specific repos."""

    repo_ids: list[uuid.UUID] = Field(default_factory=list)


class DesignHtmlUpdate(BaseModel):
    """Schema for manually editing a design's HTML or notes."""

    design_html: str | None = None
    notes: str | None = None


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


class CodeReviewRepoStatus(BaseModel):
    """Per-repo status row shown on the Code Review tab."""

    repo_id: str
    repo_name: str
    pr_number: int | None = None
    pr_state: str  # "not_raised" | "open" | "merged" | "closed"
    pr_url: str | None = None
    comment_count: int


class CodeReviewStatusResponse(BaseModel):
    """Response for GET /buds/{id}/code-review/status."""

    repos: list[CodeReviewRepoStatus]


class CodeReviewOverrideRequest(BaseModel):
    """Body for POST /buds/{id}/code-review/override.

    Forces a BUD from code_review → testing with a user-supplied reason
    when the normal PR-merge-driven auto-transition doesn't apply (e.g.
    docs-only changes, manual merges, or exceptional escalations).
    """

    reason: str = Field(..., min_length=10, max_length=2000)


class LinkedFeatureRead(BaseModel):
    """One feature linked to a BUD, with PRIMARY-repo metadata flattened.

    Shape is camelCase via ``model_config`` aliases so the frontend can
    consume it without renaming. ``code_locations`` is the JSONB blob
    from the PRIMARY :class:`FeatureToRepo` row — null when no PRIMARY
    junction exists (rare; happens for legacy or BUD-authored features).
    """

    id: uuid.UUID
    title: str = Field(..., alias="title")
    link_type: str = Field(..., alias="linkType")
    source: str
    repo_id: uuid.UUID | None = Field(default=None, alias="repoId")
    repo_name: str | None = Field(default=None, alias="repoName")
    code_locations: dict[str, list[str]] | None = Field(default=None, alias="codeLocations")

    model_config = {"populate_by_name": True}


class LinkFeaturesRequest(BaseModel):
    """Body for POST /buds/{bud_id}/linked-features.

    ``feature_ids`` is treated as a set — duplicates are dropped, and
    ids that don't belong to the requesting org or are inactive are
    silently filtered at the repository layer.
    """

    feature_ids: list[uuid.UUID] = Field(..., min_length=1, alias="featureIds")

    model_config = {"populate_by_name": True}


class LinkFeaturesResponse(BaseModel):
    """Response for POST /buds/{bud_id}/linked-features."""

    inserted_count: int = Field(..., alias="insertedCount")
    inserted_feature_ids: list[uuid.UUID] = Field(..., alias="insertedFeatureIds")

    model_config = {"populate_by_name": True}
