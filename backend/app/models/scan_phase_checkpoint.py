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

"""ScanPhaseCheckpoint — durable per-phase resume state.

One row per ``(scan_id, repo_id, phase, attempt)``. Written by
``checkpoint_wrap`` (``app/services/scan_checkpoints.py``) and read by
``run_scan_pipeline`` (skip-if-done short-circuit) and the
``/api/v1/skills/scan/{id}/checkpoints`` endpoint (frontend timeline).

See ``BODHIORCHARD-ARCHITECTURE.md §18.12`` for the full lifecycle.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel
from app.models.scan_phase import CheckpointStatus, ScanPhase


class ScanPhaseCheckpoint(BaseModel):
    """Durable record of one phase's execution for a given scan.

    - ``repo_id`` is NULL for GLOBAL-scope phases (feature merge,
      skill remap, embedding backfill, persist results).
    - ``sha_at_run`` is set only for SHA-reusable phases and powers
      cross-scan payload reuse when the repo HEAD is unchanged.
    - ``payload`` is JSONB and holds phase-specific outputs (e.g.
      cluster list for CODE_INDEX, feature counts for B2).
    - ``attempt`` increments on retries; the UNIQUE constraint prevents
      duplicates within a single scan.
    """

    __tablename__ = "scan_phase_checkpoints"
    __table_args__ = (
        UniqueConstraint(
            "scan_id",
            "repo_id",
            "phase",
            "attempt",
            name="uq_scan_ckpt_scan_repo_phase_attempt",
        ),
        Index("ix_scan_ckpt_scan_phase", "scan_id", "phase"),
        Index("ix_scan_ckpt_org_phase_sha", "org_id", "phase", "sha_at_run"),
        Index("ix_scan_ckpt_org_status", "org_id", "status"),
        Index("ix_scan_ckpt_parent", "parent_scan_id"),
    )

    # No inline index=True here — the composite ix_scan_ckpt_scan_phase
    # covers scan_id-only lookups via leading-column match on Postgres.
    scan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    parent_scan_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    repo_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tracked_repositories.id", ondelete="SET NULL"),
        nullable=True,
    )
    phase: Mapped[ScanPhase] = mapped_column(
        Enum(
            ScanPhase,
            name="scan_phase",
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=False,
    )
    status: Mapped[CheckpointStatus] = mapped_column(
        Enum(
            CheckpointStatus,
            name="scan_checkpoint_status",
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=False,
        default=CheckpointStatus.PENDING,
    )
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sha_at_run: Mapped[str | None] = mapped_column(String(40), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )

    def __repr__(self) -> str:
        return (
            f"<ScanPhaseCheckpoint(scan={self.scan_id}, repo={self.repo_id}, "
            f"phase={self.phase}, status={self.status}, attempt={self.attempt})>"
        )
