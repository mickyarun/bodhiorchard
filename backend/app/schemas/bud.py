"""Pydantic schemas for BUD CRUD endpoints."""

import uuid
from datetime import datetime
from typing import NamedTuple

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
    metadata_: dict | None = Field(None, alias="metadata")

    model_config = {"populate_by_name": True}


class BUDUpdate(BaseModel):
    """Schema for updating an existing BUD."""

    title: str | None = Field(None, min_length=1, max_length=500)
    status: str | None = None
    requirements_md: str | None = None
    tech_spec_md: str | None = None
    test_plan_md: str | None = None
    metadata_: dict | None = Field(None, alias="metadata")
    assignee_id: uuid.UUID | None = None

    model_config = {"populate_by_name": True}


class BUDDesignRead(BaseModel):
    """Schema for reading a BUD design wireframe."""

    id: uuid.UUID
    bud_id: uuid.UUID
    repo_id: uuid.UUID | None = None
    repo_name: str | None = None
    design_html: str | None = None
    design_path: str | None = None
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
    def extract_skill_slug(cls, data: object) -> object:
        """Pull skill_slug from the joined AgentSkill relationship."""
        if hasattr(data, "skill") and data.skill is not None:
            data.skill_slug = data.skill.skill_slug  # type: ignore[union-attr]
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
    designs: list[BUDDesignRead] = []
    metadata: dict | None = Field(None, validation_alias="metadata_")
    impacted_repos: list[dict] | None = None
    assignee_id: uuid.UUID | None = None
    assignee_name: str | None = None
    active_agent_task: BUDAgentTaskRead | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True, "populate_by_name": True}

    @model_validator(mode="before")
    @classmethod
    def extract_assignee_name(cls, data: object) -> object:
        """Pull assignee name from the joined User relationship."""
        if hasattr(data, "assignee") and data.assignee is not None:
            data.assignee_name = data.assignee.name  # type: ignore[union-attr]
        return data


class BUDListItem(BaseModel):
    """Schema for BUD list view (no full content)."""

    id: uuid.UUID
    bud_number: int
    title: str
    status: str
    assignee_id: uuid.UUID | None = None
    assignee_name: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @model_validator(mode="before")
    @classmethod
    def extract_assignee_name(cls, data: object) -> object:
        """Pull assignee name from the joined User relationship."""
        if hasattr(data, "assignee") and data.assignee is not None:
            data.assignee_name = data.assignee.name  # type: ignore[union-attr]
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
    detail: dict | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
