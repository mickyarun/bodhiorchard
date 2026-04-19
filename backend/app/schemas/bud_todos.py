# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Pydantic schemas for BUD TODO endpoints."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.bud_todo import BUDTodoStatus


class BUDTodoRead(BaseModel):
    """A single TODO as returned to the UI / MCP consumers."""

    id: uuid.UUID
    bud_id: uuid.UUID = Field(alias="budId")
    sequence: int
    title: str
    phase: str
    status: str
    is_checkpoint: bool = Field(alias="isCheckpoint")
    assignee_id: uuid.UUID | None = Field(default=None, alias="assigneeId")
    assignee_name: str | None = Field(default=None, alias="assigneeName")
    context_md: str | None = Field(default=None, alias="contextMd")
    summary: str | None = None
    taken_at: datetime | None = Field(default=None, alias="takenAt")
    detail: dict | None = None
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
    previous_assignee_id: uuid.UUID | None = Field(
        default=None, alias="previousAssigneeId"
    )

    model_config = ConfigDict(populate_by_name=True)
