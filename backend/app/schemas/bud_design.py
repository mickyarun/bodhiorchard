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

"""Pydantic schemas for per-BUD design wireframe rows.

Split out of :mod:`app.schemas.bud` so the design-tab DTOs live next to
their endpoint (``api/v1/bud_designs.py``). :class:`BUDDesignRead` is
re-exported from :mod:`app.schemas.bud` because :class:`BUDRead.designs`
embeds it; new code should import it from here.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class BUDDesignRead(BaseModel):
    """Schema for reading a BUD design wireframe."""

    id: uuid.UUID
    bud_id: uuid.UUID
    repo_id: uuid.UUID | None = None
    repo_name: str | None = None
    design_html: str | None = None
    notes: str | None = None
    status: str
    job_id: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DesignGenerateRequest(BaseModel):
    """Schema for requesting design generation for specific repos."""

    repo_ids: list[uuid.UUID] = Field(default_factory=list)


class DesignHtmlUpdate(BaseModel):
    """Schema for manually editing a design's HTML or notes."""

    design_html: str | None = None
    notes: str | None = None
