# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Junction between :class:`Feature` and :class:`TrackedRepository`.

Replaces the single ``synthesized_features.repo_id`` column. Each row
records the relationship a single repo has with a feature:

* ``PRIMARY``  — the repo where the feature was synthesised (one per
  feature). Carries ``code_locations`` listing the source files that
  belong to the feature.
* ``BACKEND``  — a backend repo whose declared routes the frontend
  feature calls. Carries ``api_paths`` (the matched normalised routes).

A repo that is both the synthesis source and a backend target appears as
a single ``PRIMARY`` row with ``api_paths`` populated — the role is the
strongest description of the relationship, not the only one.
"""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.feature import Feature


class FeatureToRepoRole(StrEnum):
    """Why a repo is linked to a feature."""

    PRIMARY = "primary"
    BACKEND = "backend"


class FeatureToRepo(Base):
    """One feature ↔ one repo, with the role and supporting metadata."""

    __tablename__ = "feature_to_repo"
    __table_args__ = (
        UniqueConstraint("feature_id", "repo_id", name="uq_ftr_feature_repo"),
        Index("ix_ftr_feature_id", "feature_id"),
        Index("ix_ftr_repo_id", "repo_id"),
        Index("ix_ftr_feature_role", "feature_id", "role"),
        # Per-repo unique on PRIMARY rows. Denormalised ``feature_title``
        # makes this expressible at the DB level (Postgres unique indexes
        # can't reference another table). Cross-repo title reuse stays
        # legal — only the (repo, title) PRIMARY combination is unique.
        Index(
            "ux_ftr_primary_title",
            "repo_id",
            "feature_title",
            unique=True,
            postgresql_where=text("role = 'primary'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # No inline ``index=True`` here — the named index ``ix_ftr_feature_id``
    # is declared in ``__table_args__`` so the ORM model and the alembic
    # migration agree on the index name (autogenerate would otherwise want
    # to drop+recreate as ``ix_feature_to_repo_feature_id``).
    feature_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("features.id", ondelete="CASCADE"),
        nullable=False,
    )
    repo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tracked_repositories.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[FeatureToRepoRole] = mapped_column(
        Enum(
            FeatureToRepoRole,
            name="feature_to_repo_role",
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=False,
    )
    # Denormalised from ``Feature.feature_title`` so the partial unique
    # index on (repo_id, feature_title) WHERE role='primary' can live at
    # the DB level — Postgres can't enforce uniqueness across a join.
    # Features are immutable in the live pipeline (the synth writer never
    # mutates a row, only inserts new ones), so denormalisation is safe.
    feature_title: Mapped[str] = mapped_column(String(500), nullable=False)
    # Source-side files (PRIMARY rows) — same JSON shape as the legacy
    # ``synthesized_features.code_locations`` (e.g. ``{"frontend":
    # ["..."], "backend": ["..."]}``) so existing readers keep working.
    code_locations: Mapped[dict[str, list[str]] | None] = mapped_column(JSONB, nullable=True)
    # Linked backend routes (BACKEND rows) — normalised paths produced by
    # the ``backend_link`` stage's extractor (``:param`` placeholders).
    api_paths: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    feature: Mapped["Feature"] = relationship(back_populates="repo_links")

    def __repr__(self) -> str:
        return f"<FeatureToRepo(feature={self.feature_id}, repo={self.repo_id}, role={self.role})>"
