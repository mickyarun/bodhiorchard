# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Pydantic schemas for permissions and roles."""

import uuid

from pydantic import BaseModel, Field


class PermissionRead(BaseModel):
    """Schema for reading a single permission."""

    id: uuid.UUID
    name: str
    resource_id: str
    description: str | None = None
    category_key: str
    display_order: int

    model_config = {"from_attributes": True}


class PermissionCategoryRead(BaseModel):
    """Schema for reading a permission category with nested permissions."""

    key: str
    name: str
    description: str | None = None
    display_order: int
    permissions: list[PermissionRead]

    model_config = {"from_attributes": True}


class RoleRead(BaseModel):
    """Schema for reading a role with its permissions."""

    id: uuid.UUID
    name: str
    description: str | None = None
    scope_type: str
    is_active: bool
    permissions: list[PermissionRead]

    model_config = {"from_attributes": True}


class RoleCreate(BaseModel):
    """Schema for creating a custom role."""

    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = None
    permission_ids: list[uuid.UUID]


class RoleUpdate(BaseModel):
    """Schema for updating a role."""

    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = None
    permission_ids: list[uuid.UUID] | None = None
