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
    avatar_url: str | None = Field(None, alias="avatarUrl")
    github_username: str | None = Field(None, alias="githubUsername")
    is_active: bool = Field(True, alias="isActive")
    created_at: str = Field("", alias="createdAt")
    email_aliases: list[str] = Field(default_factory=list, alias="emailAliases")

    model_config = {"populate_by_name": True, "from_attributes": True}


class AssignRoleRequest(BaseModel):
    """Request to assign an RBAC role to a user."""

    role_id: uuid.UUID = Field(alias="roleId")

    model_config = {"populate_by_name": True}


class AddMemberRequest(BaseModel):
    """Request to add a new member to the organization."""

    email: str = Field(..., min_length=1, max_length=320)
    name: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=6)
    role_id: uuid.UUID | None = Field(None, alias="roleId")
    avatar_url: str | None = Field(None, alias="avatarUrl", max_length=500)
    github_username: str | None = Field(None, alias="githubUsername", max_length=100)

    model_config = {"populate_by_name": True}


class UpdateCharacterRequest(BaseModel):
    """Request to update a member's garden character model preference."""

    character_model: str | None = Field(
        None,
        alias="characterModel",
        max_length=100,
        description="GLB filename (e.g. 'developer.glb') or null to reset to random",
    )

    model_config = {"populate_by_name": True}


class MergeMembersRequest(BaseModel):
    """Request to merge a source member into a target member.

    The source member's skill profiles and email are transferred to
    the target, then the source is deactivated.
    """

    source_id: uuid.UUID = Field(alias="sourceId")

    model_config = {"populate_by_name": True}
