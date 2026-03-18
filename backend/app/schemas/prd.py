"""Pydantic schemas for PRD CRUD endpoints."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class PRDCreate(BaseModel):
    """Schema for creating a new PRD."""

    title: str = Field(..., min_length=1, max_length=500)
    content_md: str | None = None
    metadata_: dict | None = Field(None, alias="metadata")

    model_config = {"populate_by_name": True}


class PRDUpdate(BaseModel):
    """Schema for updating an existing PRD."""

    title: str | None = Field(None, min_length=1, max_length=500)
    status: str | None = None
    content_md: str | None = None
    tech_spec_md: str | None = None
    test_plan_md: str | None = None
    metadata_: dict | None = Field(None, alias="metadata")

    model_config = {"populate_by_name": True}


class PRDRead(BaseModel):
    """Schema for reading a single PRD with full content."""

    id: uuid.UUID
    org_id: uuid.UUID
    prd_number: int
    title: str
    status: str
    content_md: str | None = None
    tech_spec_md: str | None = None
    test_plan_md: str | None = None
    metadata_: dict | None = Field(None, alias="metadata")
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True, "populate_by_name": True}


class PRDListItem(BaseModel):
    """Schema for PRD list view (no full content)."""

    id: uuid.UUID
    prd_number: int
    title: str
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
