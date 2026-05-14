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

"""Pydantic schemas for permissions.

Role schemas (``RoleRead``, ``RoleCreate``, ``RoleUpdate``) live in
``schemas/role.py`` so role-specific fields like ``base_role`` stay
co-located with the Role concept.
"""

import uuid

from pydantic import BaseModel


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
