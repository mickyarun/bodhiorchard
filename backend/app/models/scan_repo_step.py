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

"""ScanRepoStep — one phase execution inside one repo run.

This is the row that drives the scan timeline UI: each repo lane shows
11 step chips, status-coloured, with hover tooltips populated from
``input_count`` / ``kept_count`` / ``dropped_count`` / ``extras``.

Resume is implemented on top of these rows: the workflow finds the
last successful step per repo, marks earlier steps ``SKIPPED_CACHE``,
and re-runs from the next one.
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
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel
from app.models.scan_phase import ScanPhase
from app.models.scan_run_enums import StepStatus


class ScanRepoStep(BaseModel):
    """One phase execution inside one repo run."""

    __tablename__ = "scan_repo_steps"
    __table_args__ = (
        UniqueConstraint(
            "scan_repo_run_id",
            "phase",
            name="uq_scan_repo_step_run_phase",
        ),
        Index(
            "ix_scan_repo_step_run_status",
            "scan_repo_run_id",
            "status",
        ),
    )

    scan_repo_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("scan_repo_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    phase: Mapped[ScanPhase] = mapped_column(
        Enum(
            ScanPhase,
            name="scan_phase",
            values_callable=lambda e: [x.value for x in e],
            create_type=False,
        ),
        nullable=False,
    )
    status: Mapped[StepStatus] = mapped_column(
        Enum(
            StepStatus,
            name="step_status",
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=False,
        default=StepStatus.QUEUED,
        server_default=StepStatus.QUEUED.value,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    input_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    kept_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    dropped_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    extras: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<ScanRepoStep(run={self.scan_repo_run_id}, phase={self.phase}, "
            f"status={self.status})>"
        )
