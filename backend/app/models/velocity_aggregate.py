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

"""Per-bucket rolling velocity aggregates for the estimator.

One row per ``(org_id, complexity, phase)``. Each row keeps a
fixed-window list of recent actual-phase-durations plus precomputed
percentiles, a PERT triple, and Welford running mean / M2 so the
estimator can read a single row instead of scanning hundreds of
``feature_learnings`` rows on every estimation call.

Updates are incremental — ``bud_metrics.compute_and_persist`` calls
``velocity_aggregate_writer.roll_bud_into_aggregates`` after each BUD
closes, which does one upsert per phase. The pattern follows the
"online bootstrap" literature for streaming forecasters (see
https://arxiv.org/pdf/2310.19683).
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel
from app.models.bud import BUDStatus


class VelocityAggregate(BaseModel):
    """One ``(complexity, phase)`` bucket of rolling per-BUD actuals for an org."""

    __tablename__ = "velocity_aggregates"
    __table_args__ = (
        UniqueConstraint(
            "org_id",
            "complexity",
            "phase",
            name="uq_velocity_agg_bucket",
        ),
        Index("ix_velocity_agg_lookup", "org_id", "complexity"),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id"),
        nullable=False,
        index=True,
    )
    complexity: Mapped[int] = mapped_column(Integer, nullable=False)
    # ``values_callable`` mirrors what ``BUDDocument.status`` does: the
    # existing ``bud_status`` Postgres enum holds the .value strings
    # ('bud', 'design', ...), not the Python enum names ('BUD',
    # 'DESIGN', ...). Without this kwarg SQLAlchemy serializes by name
    # and every INSERT fails with InvalidTextRepresentationError.
    phase: Mapped[BUDStatus] = mapped_column(
        Enum(
            BUDStatus,
            name="bud_status",
            create_type=False,
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=False,
    )
    n_samples: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    # Rolling window of the most recent ``SAMPLE_WINDOW_CAP`` actual_days
    # values, used to re-derive percentiles cheaply on each insert.
    sample_window: Mapped[list[float]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    # BUD ids that have already contributed to this bucket. Keeps the
    # incremental update idempotent against PROD->CLOSED double-fire and
    # webhook re-deliveries. Capped to ``SAMPLE_WINDOW_CAP`` to bound
    # the row size — old ids fall out of the dedup set as the window
    # rotates. That rotation is ONLY safe because the upstream guard in
    # ``bud_metrics.compute_and_persist`` short-circuits the whole
    # pipeline once ``feature_learnings.metrics`` is non-null, so a
    # dropped bud_id can never get re-rolled into the bucket. Window
    # and dedup list rotate in lockstep — never adjust one without the
    # other.
    contributing_bud_ids: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    p50_days: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    p70_days: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    p85_days: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    pert_optimistic: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    pert_most_likely: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    pert_pessimistic: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    # Welford online mean / variance. Independent of the rolling window so
    # we can observe long-horizon drift even after the window rotates.
    running_mean: Mapped[float] = mapped_column(
        Numeric(10, 4), nullable=False, default=0, server_default="0"
    )
    running_m2: Mapped[float] = mapped_column(
        Numeric(12, 4), nullable=False, default=0, server_default="0"
    )
    # Snapshot of ``running_mean`` from 30 days ago, advanced once a day
    # by ``mcp_audit_cleanup.daily_velocity_snapshot_roll``. Drives the
    # ``trend_30d`` field in the org-level overview.
    running_mean_30d_ago: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    snapshot_taken_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:
        return (
            f"<VelocityAggregate(org_id={self.org_id}, complexity={self.complexity}, "
            f"phase={self.phase!s}, n={self.n_samples})>"
        )
