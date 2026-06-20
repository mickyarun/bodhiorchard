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

"""Pydantic schemas for the Bug CRUD endpoints and the bug comment thread."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

BugSeverityValue = Literal["low", "medium", "high", "critical"]
BugStatusValue = Literal["open", "in-progress", "resolved", "closed", "blocked", "rejected"]
BugTypeValue = Literal["testing", "production"]


class BugCreate(BaseModel):
    """Request body for creating a bug.

    The two link fields (``bud_id``, ``feature_id``) are both optional.
    Callers from the BUDBugsPanel pass ``bud_id``; callers from the
    /bugs production Kanban pass ``feature_id`` (or neither, letting
    the AI linker auto-resolve from ``bug_type``).
    """

    title: str = Field(max_length=500)
    description: str | None = Field(None, max_length=10000)
    severity: BugSeverityValue = "medium"
    module: str | None = Field(None, max_length=255)
    bud_id: str | None = Field(None, alias="budId")
    feature_id: str | None = Field(None, alias="featureId")
    bug_type: BugTypeValue | None = Field(None, alias="bugType")

    model_config = {"populate_by_name": True}

    @model_validator(mode="after")
    def _reject_feature_link_with_testing_type(self) -> "BugCreate":
        """``bug_type='testing'`` against a ``feature_id`` is incoherent.

        Features are shipped registry entries; bugs against them are
        production-class by definition. Reject the combination at the
        boundary so we never persist a self-contradicting row.
        """
        if self.feature_id is not None and self.bug_type == "testing":
            raise ValueError(
                "bug_type='testing' cannot be combined with featureId — "
                "Feature-linked bugs are production-class."
            )
        return self


class BugUpdate(BaseModel):
    """Request body for updating a bug (all fields optional)."""

    title: str | None = Field(None, max_length=500)
    description: str | None = Field(None, max_length=10000)
    status: BugStatusValue | None = None
    severity: BugSeverityValue | None = None
    assignee_id: str | None = Field(None, alias="assigneeId")
    module: str | None = Field(None, max_length=255)
    linked_pr: str | None = Field(None, alias="linkedPr", max_length=500)
    bud_id: str | None = Field(None, alias="budId")
    feature_id: str | None = Field(None, alias="featureId")

    model_config = {"populate_by_name": True}


class BugRead(BaseModel):
    """Full bug response with resolved names."""

    id: str
    bug_number: int = Field(alias="bugNumber")
    title: str
    description: str | None = None
    severity: BugSeverityValue
    status: BugStatusValue
    bug_type: BugTypeValue = Field(alias="bugType")
    module: str | None = None
    linked_pr: str | None = Field(None, alias="linkedPr")
    bud_id: str | None = Field(None, alias="budId")
    bud_number: int | None = Field(None, alias="budNumber")
    bud_title: str | None = Field(None, alias="budTitle")
    feature_id: str | None = Field(None, alias="featureId")
    feature_title: str | None = Field(None, alias="featureTitle")
    reporter_id: str = Field(alias="reporterId")
    reporter_name: str | None = Field(None, alias="reporterName")
    assignee_id: str | None = Field(None, alias="assigneeId")
    assignee_name: str | None = Field(None, alias="assigneeName")
    comment_count: int = Field(0, alias="commentCount")
    resolved_at: datetime | None = Field(None, alias="resolvedAt")
    rejected_at: datetime | None = Field(None, alias="rejectedAt")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")

    model_config = {"populate_by_name": True}


class BugListItem(BaseModel):
    """Lightweight bug for list / board views."""

    id: str
    bug_number: int = Field(alias="bugNumber")
    title: str
    severity: BugSeverityValue
    status: BugStatusValue
    bug_type: BugTypeValue = Field(alias="bugType")
    module: str | None = None
    bud_id: str | None = Field(None, alias="budId")
    bud_number: int | None = Field(None, alias="budNumber")
    feature_id: str | None = Field(None, alias="featureId")
    feature_title: str | None = Field(None, alias="featureTitle")
    reporter_name: str | None = Field(None, alias="reporterName")
    assignee_id: str | None = Field(None, alias="assigneeId")
    assignee_name: str | None = Field(None, alias="assigneeName")
    comment_count: int = Field(0, alias="commentCount")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")

    model_config = {"populate_by_name": True}


class BugListResponse(BaseModel):
    """Paginated bug list response."""

    items: list[BugListItem]
    total: int
    page: int
    page_size: int = Field(alias="pageSize")

    model_config = {"populate_by_name": True}


class BugBoardResponse(BaseModel):
    """Bugs grouped by status for the production Kanban board.

    Each key is a :data:`BugStatusValue`; the value is the bugs in that
    column, newest-first. Frontend renders one column per key in the
    order ``open → in-progress → blocked → resolved → closed``.
    """

    columns: dict[str, list[BugListItem]]
    total: int

    model_config = {"populate_by_name": True}


# ── Comment thread ────────────────────────────────────────────────────


class BugCommentCreate(BaseModel):
    """Request body for posting a new comment to a bug."""

    body: str = Field(min_length=1, max_length=10000)

    model_config = {"populate_by_name": True}


class BugCommentUpdate(BaseModel):
    """Request body for editing an existing comment.

    Only ``body`` is editable; ``deleted_at`` is set via the DELETE
    endpoint (soft-delete with tombstone render).
    """

    body: str = Field(min_length=1, max_length=10000)

    model_config = {"populate_by_name": True}


class BugCommentRead(BaseModel):
    """Single comment in a bug's thread.

    ``deleted_at`` distinguishes a tombstone from a normal comment; the
    UI renders ``[deleted]`` in place of ``body`` when set. ``edited_at``
    drives the "(edited)" label.
    """

    id: str
    bug_id: str = Field(alias="bugId")
    author_id: str = Field(alias="authorId")
    author_name: str | None = Field(None, alias="authorName")
    body: str
    edited_at: datetime | None = Field(None, alias="editedAt")
    deleted_at: datetime | None = Field(None, alias="deletedAt")
    created_at: datetime = Field(alias="createdAt")

    model_config = {"populate_by_name": True}


class BugCommentListResponse(BaseModel):
    """Thread of comments on a bug, oldest first."""

    items: list[BugCommentRead]
    total: int

    model_config = {"populate_by_name": True}
