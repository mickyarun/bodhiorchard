# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""``FeatureMatchLog`` — append-only audit trail of reconciler decisions.

The reconciler matches each ``FeatureWrite`` to an existing row via a
layered strategy: exact ``cluster_signature`` (1.0), then Jaccard over
``code_locations`` (≥ 0.7), then embedding cosine (≥ 0.85). One row is
recorded here per write so the thresholds can be tuned from real data.

Use cases:
- ``GET /v1/features/match-debug?match_via=jaccard&score_min=0.6&score_max=0.79``
  surfaces borderline Jaccard matches for review.
- Same pattern for cosine borderlines (``score_min=0.78&score_max=0.86``).

Append-only: rows are never updated. Volume scales with feature count
× scan count; cleanup left to a future ``pg_cron`` job if the table
grows beyond a working-set query size.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class FeatureMatchLog(Base):
    """One row per reconciler match decision. Append-only."""

    __tablename__ = "feature_match_log"
    __table_args__ = (
        Index("ix_fml_org_repo_created", "org_id", "repo_id", text("created_at DESC")),
        Index("ix_fml_org_via_score", "org_id", "match_via", "score"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    repo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tracked_repositories.id", ondelete="CASCADE"),
        nullable=False,
    )
    head_sha: Mapped[str] = mapped_column(String(64), nullable=False)
    match_via: Mapped[str] = mapped_column(String(16), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    feature_title: Mapped[str] = mapped_column(String(500), nullable=False)
    matched_feature_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("features.id", ondelete="SET NULL"),
        nullable=True,
    )
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<FeatureMatchLog(match_via={self.match_via!r}, "
            f"score={self.score:.3f}, decision={self.decision!r})>"
        )
