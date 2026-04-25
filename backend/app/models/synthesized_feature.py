# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""SynthesizedFeature — immutable per-scan pre-merge feature record.

Written once by the MCP ``write_feature_registry`` handler during
``FEATURE_SYNTHESIS``, never mutated by merge (only ``merge_outcome``
is updated). Superseded rows are marked with ``superseded_at`` but
never hard-deleted — this is the durable audit trail that makes
bad-merge recovery, per-feature merge visibility, and synthesis-queue
self-heal possible.

Relationship to existing tables:

- ``knowledge_items`` is the current, deduplicated, post-merge view
  (what the UI reads).
- ``knowledge_to_repo`` is the current junction with ``code_locations``
  (also post-merge).
- ``synthesized_features`` is the historical, append-only,
  pre-merge record — the arbiter of truth when the two drift.

See ``BODHIORCHARD-ARCHITECTURE.md §18.12``.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel
from app.models.scan_phase import MergeOutcome


class SynthesizedFeature(BaseModel):
    """One row per feature Claude wrote for a given (scan, repo) pair."""

    __tablename__ = "synthesized_features"
    __table_args__ = (
        Index("ix_synth_feat_scan_repo", "scan_id", "repo_id"),
        Index("ix_synth_feat_repo_title", "org_id", "repo_id", "feature_title"),
        Index("ix_synth_feat_merged_into", "merged_into_id"),
        Index(
            "ix_synth_feat_latest",
            "org_id",
            "repo_id",
            postgresql_where=text("superseded_at IS NULL"),
        ),
        Index("ix_synth_feat_scan_outcome", "scan_id", "merge_outcome"),
    )

    # No inline index=True — the composite ix_synth_feat_scan_repo
    # covers scan_id-only lookups via leading-column match on Postgres.
    scan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    repo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tracked_repositories.id", ondelete="CASCADE"),
        nullable=False,
    )
    feature_title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    capabilities: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    cluster_names: Mapped[list[str]] = mapped_column(
        ARRAY(String),
        nullable=False,
        default=list,
        server_default=text("ARRAY[]::varchar[]"),
    )
    code_locations: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    knowledge_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_items.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Outcome assigned during FEATURE_MERGE. NULL means the merge pass
    # hasn't run yet for this row. When MERGED_INTO, the companion
    # ``merged_into_id`` FK points at the surviving canonical row —
    # keeping them as two columns preserves referential integrity and
    # makes "show me every row consolidated into X" a single indexed join.
    merge_outcome: Mapped[MergeOutcome | None] = mapped_column(
        Enum(
            MergeOutcome,
            name="synth_feat_merge_outcome",
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=True,
    )
    merged_into_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("synthesized_features.id", ondelete="SET NULL"),
        nullable=True,
    )
    synthesized_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<SynthesizedFeature(scan={self.scan_id}, repo={self.repo_id}, "
            f"title={self.feature_title!r}, outcome={self.merge_outcome})>"
        )
