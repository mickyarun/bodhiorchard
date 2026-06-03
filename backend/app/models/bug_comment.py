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

"""Comment thread on a :class:`app.models.bug.Bug`."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class BugComment(BaseModel):
    """A single comment on a bug.

    Soft-deleted via ``deleted_at`` (kept for audit + tombstone render in
    the UI). ``edited_at`` is stamped on every PATCH so the UI can show
    "(edited)".
    """

    __tablename__ = "bug_comments"
    __table_args__ = (
        Index("ix_bug_comments_bug_created", "bug_id", "created_at"),
        Index("ix_bug_comments_org", "org_id"),
    )

    bug_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bugs.id", ondelete="CASCADE"), nullable=False
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    author_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<BugComment(id={self.id}, bug_id={self.bug_id})>"
