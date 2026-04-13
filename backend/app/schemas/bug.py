"""Pydantic schemas for the Bug CRUD endpoints."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

BugSeverityValue = Literal["low", "medium", "high", "critical"]
BugStatusValue = Literal["open", "in-progress", "resolved", "closed", "blocked"]
BugTypeValue = Literal["testing", "production"]


class BugCreate(BaseModel):
    """Request body for creating a bug."""

    title: str = Field(max_length=500)
    description: str | None = None
    severity: BugSeverityValue = "medium"
    module: str | None = Field(None, max_length=255)
    bud_id: str | None = Field(None, alias="budId")

    model_config = {"populate_by_name": True}


class BugUpdate(BaseModel):
    """Request body for updating a bug (all fields optional)."""

    title: str | None = Field(None, max_length=500)
    description: str | None = None
    status: BugStatusValue | None = None
    severity: BugSeverityValue | None = None
    assignee_id: str | None = Field(None, alias="assigneeId")
    module: str | None = None
    linked_pr: str | None = Field(None, alias="linkedPr")
    bud_id: str | None = Field(None, alias="budId")

    model_config = {"populate_by_name": True}


class BugRead(BaseModel):
    """Full bug response with resolved names."""

    id: str
    title: str
    description: str | None = None
    severity: BugSeverityValue
    status: BugStatusValue
    bug_type: BugTypeValue = Field(alias="bugType")
    module: str | None = None
    linked_pr: str | None = Field(None, alias="linkedPr")
    bud_id: str | None = Field(None, alias="budId")
    bud_number: int | None = Field(None, alias="budNumber")
    bud_title: str | None = Field(None, alias="budTitle")
    reporter_id: str = Field(alias="reporterId")
    reporter_name: str | None = Field(None, alias="reporterName")
    assignee_id: str | None = Field(None, alias="assigneeId")
    assignee_name: str | None = Field(None, alias="assigneeName")
    resolved_at: datetime | None = Field(None, alias="resolvedAt")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")

    model_config = {"populate_by_name": True}


class BugListItem(BaseModel):
    """Lightweight bug for list views."""

    id: str
    title: str
    severity: BugSeverityValue
    status: BugStatusValue
    bug_type: BugTypeValue = Field(alias="bugType")
    module: str | None = None
    bud_id: str | None = Field(None, alias="budId")
    bud_number: int | None = Field(None, alias="budNumber")
    reporter_name: str | None = Field(None, alias="reporterName")
    assignee_name: str | None = Field(None, alias="assigneeName")
    created_at: datetime = Field(alias="createdAt")

    model_config = {"populate_by_name": True}


class BugListResponse(BaseModel):
    """Paginated bug list response."""

    items: list[BugListItem]
    total: int
    page: int
    page_size: int = Field(alias="pageSize")

    model_config = {"populate_by_name": True}
