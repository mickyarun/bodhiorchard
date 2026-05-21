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

"""Append-only edit history for BUDDocument.

One row per BUD content mutation. Versioning is scoped per ``(bud_id,
phase)`` because each lifecycle phase owns a different markdown field
(see :mod:`app.services.bud_edit_policy`) — a user reverting the design
document should not silently roll back ``requirements_md`` from two
phases ago.

Retention is capped at ``MAX_VERSIONS_PER_PHASE`` newest **non-revert**
rows per ``(bud_id, phase)``; revert rows don't count against the cap so
a revert-storm can't evict real edits. Pruning happens inside the same
transaction as the snapshot insert (see
:func:`app.repositories.bud_version.snapshot_and_prune`).
"""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.bud import BUDStatus

MAX_VERSIONS_PER_PHASE = 20


class BUDEditSource(StrEnum):
    """Origin of a BUD content edit.

    ``revert`` is distinct from ``ui`` so the prune query can exclude
    revert snapshots from the per-phase cap — otherwise clicking revert
    repeatedly would evict real edit history.
    """

    UI = "ui"
    MCP = "mcp"
    AGENT = "agent"
    MIGRATION = "migration"
    REVERT = "revert"


class BUDVersion(Base):
    """Pre-edit snapshot of a BUDDocument's mutable content."""

    __tablename__ = "bud_versions"
    __table_args__ = (
        UniqueConstraint("bud_id", "phase", "version_no", name="uq_bud_version_per_phase"),
        Index("ix_bud_version_phase_latest", "bud_id", "phase", "version_no"),
        Index("ix_bud_version_recent", "bud_id", "edited_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    bud_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bud_documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    phase: Mapped[BUDStatus] = mapped_column(
        Enum(BUDStatus, name="bud_status", values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    source: Mapped[BUDEditSource] = mapped_column(
        Enum(
            BUDEditSource,
            name="bud_edit_source",
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=False,
    )
    edited_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    mcp_token_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user_mcp_tokens.id", ondelete="SET NULL"), nullable=True
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    edited_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<BUDVersion(bud_id={self.bud_id}, phase={self.phase}, "
            f"v={self.version_no}, source={self.source})>"
        )
