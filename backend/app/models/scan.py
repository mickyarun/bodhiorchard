# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Scan model — durable row-per-scan progress state.

Replaces the Redis hash (``scan:{scan_id}``) and secondary index
(``scan_active:{org_id}``) that ``app/services/scan_progress.py`` used
to manage. One row per scan_id, updated in place as the pipeline makes
progress. Stale scans are auto-detected by ``updated_at`` age on read
rather than by key TTL.

The per-phase detail continues to live in ``scan_phase_checkpoints``.
This table holds the aggregate fields the UI needs for the progress
bar + the "latest scan" query.
"""

from __future__ import annotations

import uuid
from enum import StrEnum

from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class ScanAggregateStatus(StrEnum):
    """Terminal + transient states the API surfaces for a scan.

    Mirrors the string values the Redis implementation already emitted
    so no frontend change is needed.
    """

    STARTED = "started"
    CHECKING_OUT = "checking_out"
    ANALYZING_CHANGES = "analyzing_changes"
    INDEXING_CODE = "indexing_code"
    SETTING_UP_INDEX = "setting_up_index"
    SETTING_UP_WORKTREES = "setting_up_worktrees"
    SETTING_UP_MCP = "setting_up_mcp"
    INSTALLING_HOOKS = "installing_hooks"
    PUSHING_SETUP = "pushing_setup"
    CLEANING_STALE = "cleaning_stale"
    ANALYZING_SKILLS = "analyzing_skills"
    EXTRACTING_DESIGN_SYSTEM = "extracting_design_system"
    SYNTHESIZING_FEATURES = "synthesizing_features"
    GENERATING_EMBEDDINGS = "generating_embeddings"
    MERGING_FEATURES = "merging_features"
    REMAPPING_SKILLS = "remapping_skills"
    SAVING_RESULTS = "saving_results"
    FINALIZING = "finalizing"
    FINALIZING_REPO = "finalizing_repo"
    COMPLETED = "completed"
    FAILED = "failed"


# Non-terminal states mean "scan is still making progress". Used by
# ``get_active_scan_for_org`` to filter out completed/failed rows.
ACTIVE_SCAN_STATUSES: frozenset[ScanAggregateStatus] = frozenset(
    s
    for s in ScanAggregateStatus
    if s
    not in (
        ScanAggregateStatus.COMPLETED,
        ScanAggregateStatus.FAILED,
    )
)


class Scan(BaseModel):
    """One row per scan, holds aggregate progress state for the UI."""

    __tablename__ = "scans"
    __table_args__ = (
        Index("ix_scans_org_created", "org_id", "created_at"),
        Index("ix_scans_org_updated", "org_id", "updated_at"),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    parent_scan_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    # Python-side defaults mirror ``server_default`` so a freshly-
    # constructed ``Scan()`` has the same shape the DB would materialise
    # on INSERT. Matters for unit tests that build instances directly
    # and for any caller that reads a partially-populated row.
    status: Mapped[str] = mapped_column(
        String(64), nullable=False, default="started", server_default="started"
    )
    scan_mode: Mapped[str] = mapped_column(
        String(16), nullable=False, default="full", server_default="full"
    )
    progress_pct: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    features_indexed: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    features_skipped: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    profiles_found: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    stale_cleaned: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    unmatched_authors: Mapped[list[str]] = mapped_column(
        ARRAY(String),
        nullable=False,
        default=list,
        server_default="{}",
    )
    synthesis_warning: Mapped[str | None] = mapped_column(Text, nullable=True)
    setup_pr_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # JSONB array of {repo, phase, summary, hint?} dicts. Appended via
    # ``repo_warnings || $1::jsonb`` so concurrent writers compose
    # without lost updates.
    repo_warnings: Mapped[list[dict]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
    )

    def __repr__(self) -> str:
        return f"<Scan(id={self.id}, org={self.org_id}, status={self.status})>"
