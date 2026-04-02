"""Pydantic schemas for user endpoints."""

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.models.user import UserRole


class UserCreate(BaseModel):
    """Schema for creating a new user."""

    email: EmailStr
    name: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=8, max_length=128)
    role: UserRole = UserRole.DEVELOPER


class UserRead(BaseModel):
    """Schema for reading user data."""

    id: uuid.UUID
    org_id: uuid.UUID
    email: str
    name: str
    role: UserRole
    role_name: str | None = None
    permissions: list[str] = []
    slack_id: str | None = None
    github_username: str | None = None
    character_model: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    """Schema for updating a user."""

    name: str | None = Field(None, min_length=1, max_length=255)
    role: UserRole | None = None
    role_id: uuid.UUID | None = None
    slack_id: str | None = None
    github_username: str | None = None
