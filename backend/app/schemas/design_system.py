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

"""Pydantic schemas for design system CRUD endpoints."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class DesignSystemRead(BaseModel):
    """Schema for reading a design system entry with repo name."""

    id: uuid.UUID
    org_id: uuid.UUID
    repo_id: uuid.UUID
    repo_name: str | None = None
    is_default: bool
    content: str
    source_hash: str | None = None
    extracted_at: datetime
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class DesignSystemExtractRequest(BaseModel):
    """Schema for triggering design system extraction from a tracked repo."""

    repo_id: uuid.UUID
    is_default: bool = Field(False, description="Mark as org-wide default on creation")


class DesignSystemSetDefault(BaseModel):
    """Schema for marking a design system as the org default."""

    id: uuid.UUID


class DesignSystemUpdateContent(BaseModel):
    """Schema for manually updating design system content."""

    content: str = Field(..., min_length=1)
