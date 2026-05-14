# Copyright 2025-2026 Arun Rajkumar
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Pydantic schemas for roles.

Split out from ``schemas/permission.py`` so role-specific fields
(``base_role_id``) live next to the Role concept rather than the
permission-list endpoints. Permission read-models stay in
``schemas/permission.py``.
"""

import uuid

from pydantic import BaseModel, Field

from app.schemas.permission import PermissionRead


class RoleRead(BaseModel):
    """Schema for reading a role with its permissions."""

    id: uuid.UUID
    name: str
    description: str | None = None
    scope_type: str
    is_active: bool
    # FK to the seeded SYSTEM role this custom role inherits from.
    # ``None`` for system roles themselves — the assigner resolves them
    # by name.
    base_role_id: uuid.UUID | None = None
    # Convenience: the inherited system role's name (UserRole value).
    # Resolved server-side via the ``base_role`` relationship so the UI
    # doesn't need a second roundtrip to render "inherits from Tech Lead".
    base_role_name: str | None = None
    permissions: list[PermissionRead]

    model_config = {"from_attributes": True}


class RoleCreate(BaseModel):
    """Schema for creating a custom role."""

    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = None
    # Required: the seeded SYSTEM role this custom role inherits from.
    # Without it, members of the custom role would be invisible to the
    # phase auto-assigner.
    base_role_id: uuid.UUID
    # A role with zero permissions is useless and confusing — the admin
    # can't grant any access through it. Reject the empty list outright.
    permission_ids: list[uuid.UUID] = Field(..., min_length=1)


class RoleUpdate(BaseModel):
    """Schema for updating a role."""

    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = None
    # Optional — admins may retype a custom role (point it at a
    # different system role to staff a different phase). System roles
    # reject any change.
    base_role_id: uuid.UUID | None = None
    # Optional, but when present must keep at least one permission —
    # clearing all permissions effectively orphans every member of this
    # role, which is never the intent (use DELETE for that).
    permission_ids: list[uuid.UUID] | None = Field(None, min_length=1)
