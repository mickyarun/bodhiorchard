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
    slack_id: str | None = Field(None, alias="slackId")
    is_active: bool = Field(True, alias="isActive")
    must_change_password: bool = Field(False, alias="mustChangePassword")
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
        pattern=r"^([a-r]|kaykit:[a-z_]+:[0-9A-Fa-f]{6}:[0-9A-Fa-f]{6}:[0-9A-Fa-f]{6})$",
        description="Character model: single letter 'a'-'r' (legacy) or 'kaykit:id:hex:hex:hex'",
    )

    model_config = {"populate_by_name": True}


class SetPasswordRequest(BaseModel):
    """Request to generate and set a temporary password for a member.

    Optionally send the credentials via Slack DM in the same call,
    so the plaintext password never leaves the server boundary twice.
    """

    send_via: str | None = Field(
        None,
        alias="sendVia",
        pattern=r"^(slack)$",
        description="If set, send credentials via this channel after generating.",
    )

    model_config = {"populate_by_name": True}


class SetPasswordResponse(BaseModel):
    """Response after generating a temporary password for a member.

    The password field is sensitive — shown once in the UI and never stored.
    """

    password: str = Field(..., description="Sensitive: plaintext temporary password, shown once.")
    login_url: str = Field("", alias="loginUrl")
    slack_sent: bool | None = Field(None, alias="slackSent")
    slack_error: str | None = Field(None, alias="slackError")

    model_config = {"populate_by_name": True}


class MergeMembersRequest(BaseModel):
    """Request to merge a source member into a target member.

    The source member's skill profiles and email are transferred to
    the target, then the source is deactivated.
    """

    source_id: uuid.UUID = Field(alias="sourceId")

    model_config = {"populate_by_name": True}
