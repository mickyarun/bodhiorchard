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

"""Design system reference model for storing extracted frontend tokens per-org."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class DesignSystemRef(BaseModel):
    """Extracted design system tokens stored per-org, linked to a tracked repository."""

    __tablename__ = "design_system_refs"
    __table_args__ = (UniqueConstraint("org_id", "repo_id", name="uq_design_system_org_repo"),)

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    repo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tracked_repositories.id"), nullable=False
    )
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # User-authored markdown appended after ``content`` when served. Owned by
    # admins via the Settings → Design Systems UI; the extractor never writes
    # here, so re-scans and PR-merge rescans (which call ``upsert``) cannot
    # clobber it. Browser CSS cascade and the designer agent's later-wins
    # reading of ``:root`` tokens give override-of-existing semantics for free.
    custom_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    extracted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    @property
    def is_customised(self) -> bool:
        """One canonical definition shared by repo, API, and tests.

        ``set_custom_content`` normalises whitespace-only input to ``None``,
        so truthiness is correct for rows written through the repo. Rows
        written via raw SQL / bulk import still resolve correctly because
        we check ``strip()`` here rather than trusting the column shape.
        """
        return bool(self.custom_content and self.custom_content.strip())

    def __repr__(self) -> str:
        return f"<DesignSystemRef(id={self.id}, org_id={self.org_id}, default={self.is_default})>"
