"""Pydantic schemas for member listing and role assignment."""

import uuid

from pydantic import BaseModel, Field


class MemberRead(BaseModel):
    """Organization member for API response."""

    id: uuid.UUID
    email: str
    name: str
    role: str
    role_id: uuid.UUID | None = Field(None, alias="roleId")
    role_name: str | None = Field(None, alias="roleName")
    created_at: str = Field("", alias="createdAt")

    model_config = {"populate_by_name": True, "from_attributes": True}


class AssignRoleRequest(BaseModel):
    """Request to assign an RBAC role to a user."""

    role_id: uuid.UUID = Field(alias="roleId")

    model_config = {"populate_by_name": True}
