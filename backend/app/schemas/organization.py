"""Pydantic schemas for organization endpoints."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class OrganizationCreate(BaseModel):
    """Schema for creating a new organization."""

    name: str = Field(..., min_length=1, max_length=255)
    slug: str = Field(..., min_length=1, max_length=100, pattern=r"^[a-z0-9-]+$")
    config: dict | None = None


class OrganizationUpdate(BaseModel):
    """Schema for updating an organization."""

    name: str | None = Field(None, min_length=1, max_length=255)
    config: dict | None = None


class OrganizationRead(BaseModel):
    """Schema for reading organization data."""

    id: uuid.UUID
    name: str
    slug: str
    config: dict | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
