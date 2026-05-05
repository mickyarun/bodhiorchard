# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""``Feature`` — per-scan feature record (was ``SynthesizedFeature``).

Written by the MCP synthesis handler during ``FEATURE_SYNTHESIS`` and
augmented post-synthesis by the per-repo ``backend_link`` stage. The
single ``repo_id`` FK that used to live on the row is replaced by a
many-to-many junction (:class:`app.models.feature_to_repo.FeatureToRepo`):

* ``role=PRIMARY``  — the repo where the feature was synthesised. Carries
  ``code_locations``.
* ``role=BACKEND``  — a backend repo whose declared routes the frontend
  feature calls. Carries ``api_paths``.

Both rows can co-exist for the same (feature, repo) pair only via the
``role`` discriminator — the unique key is ``(feature_id, repo_id)`` so
a repo that is *both* the synthesis source and the route backend ends up
with one PRIMARY row whose ``api_paths`` is populated.

Re-synthesis wholesale-replaces the repo's feature set: the synthesise
stage calls ``FeatureRepository.delete_for_primary_repo`` before each
not-skip pass, so the table never carries historical "superseded" rows.
"""

import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
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

    Features are repo-scoped, not scan-scoped — the cross-layer scan
    pipeline writes a feature once and re-uses it across re-scans of
    the same source repo via the ``feature_to_repo`` PRIMARY junction.
    Re-synthesis wholesale-replaces the repo's feature set, so a row's
    presence implies it is current; there is no soft-delete column.
    """

    __tablename__ = "features"
    __table_args__ = (Index("ix_feature_org_title", "org_id", "feature_title"),)

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
