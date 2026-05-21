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

"""Data-access layer for BUDVersion (BUD edit history)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bud import BUDDocument, BUDStatus
from app.models.bud_version import MAX_VERSIONS_PER_PHASE, BUDEditSource, BUDVersion

# Mutable columns we capture in a snapshot. ``embedding`` is intentionally
# excluded: pgvector serialises to JSON awkwardly and is regenerated on
# revert. ``status`` is implied by ``phase`` and never written through the
# MCP path, so it isn't snapshotted either.
SNAPSHOT_FIELDS: tuple[str, ...] = (
    "title",
    "requirements_md",
    "tech_spec_md",
    "test_plan_md",
    "qa_automation_cases",
    "qa_manual_cases",
    "qa_execution_plan_md",
    "code_review_comments",
    "assignee_id",
    "auto_generate_phases",
    "metadata_",
    "impacted_repos",
)


def build_snapshot(bud: BUDDocument) -> dict[str, Any]:
    """Materialise a JSONB-safe snapshot dict from a BUD row.

    UUID assignee is stringified so the JSONB column round-trips cleanly
    without relying on the asyncpg UUID codec inside ``jsonb``.
    """
    snap: dict[str, Any] = {}
    for field in SNAPSHOT_FIELDS:
        value = getattr(bud, field, None)
        if isinstance(value, uuid.UUID):
            value = str(value)
        snap[field] = value
    return snap


async def _next_version_no(db: AsyncSession, bud_id: uuid.UUID, phase: BUDStatus) -> int:
    stmt = select(func.coalesce(func.max(BUDVersion.version_no), 0)).where(
        BUDVersion.bud_id == bud_id, BUDVersion.phase == phase
    )
    result = await db.execute(stmt)
    return int(result.scalar_one()) + 1


async def _prune_to_cap(db: AsyncSession, bud_id: uuid.UUID, phase: BUDStatus) -> None:
    """Drop the oldest non-revert rows beyond ``MAX_VERSIONS_PER_PHASE``.

    Reverts are excluded from the cap so they cannot evict real edits — a
    user clicking revert ten times in a row must not prune ten genuine
    versions in the process.
    """
    keep = (
        select(BUDVersion.id)
        .where(
            BUDVersion.bud_id == bud_id,
            BUDVersion.phase == phase,
            BUDVersion.source != BUDEditSource.REVERT,
        )
        .order_by(BUDVersion.version_no.desc())
        .limit(MAX_VERSIONS_PER_PHASE)
        .subquery()
    )
    stmt = delete(BUDVersion).where(
        BUDVersion.bud_id == bud_id,
        BUDVersion.phase == phase,
        BUDVersion.source != BUDEditSource.REVERT,
        BUDVersion.id.not_in(select(keep.c.id)),
    )
    await db.execute(stmt)


async def commit_snapshot(
    db: AsyncSession,
    *,
    bud_id: uuid.UUID,
    phase: BUDStatus,
    snapshot: dict[str, Any],
    source: BUDEditSource,
    edited_by: uuid.UUID | None,
    mcp_token_id: uuid.UUID | None = None,
    reason: str | None = None,
) -> BUDVersion:
    """Insert a previously-built snapshot row and prune to the per-phase cap.

    The snapshot dict is captured by :func:`build_snapshot` BEFORE the
    BUD is mutated; callers persist it via this function AFTER their
    guards have passed. Splitting the build from the commit lets handlers
    capture pre-state up front (free, in-memory) and still abort the
    write if a later check fails — no orphan history row, no
    post-mutation values leaking into the snapshot.

    Pruning runs in the same transaction so a crash mid-write leaves no
    orphan row.
    """
    version_no = await _next_version_no(db, bud_id, phase)
    row = BUDVersion(
        bud_id=bud_id,
        phase=phase,
        version_no=version_no,
        snapshot=snapshot,
        source=source,
        edited_by=edited_by,
        mcp_token_id=mcp_token_id,
        reason=reason,
    )
    db.add(row)
    await db.flush()
    await _prune_to_cap(db, bud_id, phase)
    return row


async def insert_snapshot(
    db: AsyncSession,
    *,
    bud: BUDDocument,
    phase: BUDStatus,
    source: BUDEditSource,
    edited_by: uuid.UUID | None,
    mcp_token_id: uuid.UUID | None = None,
    reason: str | None = None,
) -> BUDVersion:
    """Convenience: build + commit a snapshot from the BUD's CURRENT state.

    Use only when the caller is genuinely capturing pre-edit state right
    now — e.g. the MCP write handlers, which snapshot immediately before
    a single ``setattr``. PATCH handlers with multiple intermediate
    mutations should call :func:`build_snapshot` up front and
    :func:`commit_snapshot` once guards pass.
    """
    return await commit_snapshot(
        db,
        bud_id=bud.id,
        phase=phase,
        snapshot=build_snapshot(bud),
        source=source,
        edited_by=edited_by,
        mcp_token_id=mcp_token_id,
        reason=reason,
    )


async def list_for_bud(
    db: AsyncSession, bud_id: uuid.UUID, *, limit: int = 100
) -> list[BUDVersion]:
    """List version rows for a BUD, newest first. No snapshot blob filtering
    — callers should map to a thin DTO at the API layer.
    """
    stmt = (
        select(BUDVersion)
        .where(BUDVersion.bud_id == bud_id)
        .order_by(BUDVersion.edited_at.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_one(
    db: AsyncSession, bud_id: uuid.UUID, phase: BUDStatus, version_no: int
) -> BUDVersion | None:
    """Fetch a single snapshot by (bud_id, phase, version_no)."""
    stmt = select(BUDVersion).where(
        BUDVersion.bud_id == bud_id,
        BUDVersion.phase == phase,
        BUDVersion.version_no == version_no,
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()
