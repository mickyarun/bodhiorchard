# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""``Feature`` — incremental-CRUD feature record (was ``SynthesizedFeature``).

Written by the MCP synthesis handler during ``FEATURE_SYNTHESIS`` and
augmented post-synthesis by the per-repo ``backend_link`` stage. The
single ``repo_id`` FK that used to live on the row is replaced by a
many-to-many junction (:class:`app.models.feature_to_repo.FeatureToRepo`):

* ``role=PRIMARY``  — the repo where the feature was synthesised. Carries
  ``code_locations``.
* ``role=BACKEND``  — a backend repo whose declared routes the frontend
  feature calls. Carries ``api_paths``.

Lifecycle is incremental, not wipe-on-resynth: the reconciler in
:mod:`app.services.feature_reconciler` matches synthesised output to
existing rows by ``cluster_signature`` (primary) → ``code_locations``
Jaccard → embedding cosine, then UPDATEs in place, INSERTs, or marks
``is_active=False``. Removed features are preserved with
``deactivated_at`` set so revivals can reuse the same ``id`` (keeping
bug links and BUD references attached).
"""

import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel
from app.models.feature_to_repo import FeatureToRepo


class Feature(BaseModel):
    """One row per feature Claude wrote for an org.

    Features are repo-scoped and have a soft-delete lifecycle: removed
    features go ``is_active=False`` (with ``deactivated_at`` stamped) so
    they can be revived if reintroduced. The reconciler is the SOLE
    incremental writer; the synthesis writer in
    :mod:`app.mcp.synth_feature_writer` calls it after each per-repo
    synthesis batch.
    """

    __tablename__ = "features"
    __table_args__ = (
        Index("ix_feature_org_active", "org_id", "is_active"),
        Index("ix_feature_org_active_title", "org_id", "is_active", "feature_title"),
        Index("ix_feature_org_active_source", "org_id", "is_active", "source"),
        Index("ix_feature_org_active_fstatus", "org_id", "is_active", "feature_status"),
        Index("ix_feature_org_srcref", "org_id", "source_ref"),
        Index("ix_feature_org_cluster_sig", "org_id", "cluster_signature"),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
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
    tags: Mapped[list[str]] = mapped_column(
        ARRAY(String),
        nullable=False,
        default=list,
        server_default=text("ARRAY[]::varchar[]"),
    )
    # Embedding of ``feature_title + description`` (BAAI/bge-small-en-v1.5,
    # 384d). Computed once at synthesis write-time; nullable so legacy
    # pre-migration rows can be lazy-filled.
    embedding = mapped_column(Vector(384), nullable=True)
    # Reconciler primary identity key — SHA-256 of the cluster's
    # canonical (sorted) member node-ID list. Stable across SHAs when
    # the cluster's contents are unchanged. See
    # ``app.services.code_indexer.seed.cluster_signature``.
    cluster_signature: Mapped[str] = mapped_column(String(64), nullable=False)
    # Soft-delete: features removed at reconcile time are preserved
    # (with ``deactivated_at`` stamped) so revivals reuse the same id.
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Latest head SHA at which the reconciler confirmed this feature is
    # still present. Drives the "still alive?" audit without a join.
    last_seen_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Provenance discriminator: 'scan' (indexer/synthesis), 'bud'
    # (BUD lifecycle), 'mcp' (Claude-authored). Reconciler scopes
    # inactivation to ``source='scan'`` so BUD-authored rows are not
    # affected by a scan run.
    source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Free-form provenance reference: BUD-XXX, cluster id at synthesis
    # time, PR number, etc. Surfaced in MCP responses for traceability.
    source_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # BUD lifecycle status when the feature is BUD-authored:
    # ``planned`` → ``in_progress`` → ``implemented``. NULL for
    # scan-authored rows (treated as ``implemented`` on render).
    feature_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    synthesized_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    repo_links: Mapped[list[FeatureToRepo]] = relationship(
        back_populates="feature",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Feature(id={self.id}, title={self.feature_title!r})>"
