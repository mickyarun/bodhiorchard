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

"""Pydantic schemas for BUD TODO endpoints."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.bud_todo import BUDTodoStatus


class BUDTodoRead(BaseModel):
    """A single TODO as returned to the UI / MCP consumers."""

    id: uuid.UUID
    bud_id: uuid.UUID = Field(alias="budId")
    sequence: int
    title: str
    description: str | None = None
    phase: str
    status: str
    is_checkpoint: bool = Field(alias="isCheckpoint")
    repo_name: str | None = Field(default=None, alias="repoName")
    code_locations: list[str] = Field(default_factory=list, alias="codeLocations")
    assignee_id: uuid.UUID | None = Field(default=None, alias="assigneeId")
    assignee_name: str | None = Field(default=None, alias="assigneeName")
    context_md: str | None = Field(default=None, alias="contextMd")
    summary: str | None = None
    taken_at: datetime | None = Field(default=None, alias="takenAt")
    detail: dict[str, Any] | None = None
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class BUDTodoUpdate(BaseModel):
    """Partial update for a TODO."""

    status: str | None = None
    assignee_id: uuid.UUID | None = Field(default=None, alias="assigneeId")
    summary: str | None = None

    model_config = ConfigDict(populate_by_name=True)

    def validated_status(self) -> str | None:
        if self.status is None:
            return None
        if self.status not in {s.value for s in BUDTodoStatus}:
            raise ValueError(f"Invalid status: {self.status!r}")
        return self.status


class BUDTodoClaimResponse(BaseModel):
    """Response from claiming a TODO."""

    todo: BUDTodoRead
    previous_assignee_id: uuid.UUID | None = Field(default=None, alias="previousAssigneeId")

    model_config = ConfigDict(populate_by_name=True)
