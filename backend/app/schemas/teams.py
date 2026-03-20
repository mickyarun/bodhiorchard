"""Pydantic schemas for team endpoints."""

import uuid

from pydantic import BaseModel, Field


class TeamCreate(BaseModel):
    """Request to create a team."""

    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = None


class TeamUpdate(BaseModel):
    """Request to update a team."""

    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = None


class TeamMemberRead(BaseModel):
    """Team member for API response."""

    id: uuid.UUID
    user_id: uuid.UUID = Field(alias="userId")
    user_name: str = Field(alias="userName")
    email: str
    role: str

    model_config = {"populate_by_name": True, "from_attributes": True}


class TeamRead(BaseModel):
    """Team for API response."""

    id: uuid.UUID
    name: str
    description: str | None = None
    member_count: int = Field(0, alias="memberCount")
    created_at: str = Field(alias="createdAt")
    members: list[TeamMemberRead] = []

    model_config = {"populate_by_name": True, "from_attributes": True}


class AddMemberRequest(BaseModel):
    """Request to add a member to a team."""

    user_id: uuid.UUID = Field(alias="userId")
    role: str = "member"

    model_config = {"populate_by_name": True}


class AssignRoleRequest(BaseModel):
    """Request to assign an RBAC role to a user."""

    role_id: uuid.UUID = Field(alias="roleId")

    model_config = {"populate_by_name": True}
