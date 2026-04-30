# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Sandbox merge applier — mirrors ``apply_feature_merge_plan`` semantics.

Takes a (canonical, absorbed[]) merge plan from the verifier and:

1. Finds canonical KI via canonical synth row's ``knowledge_item_id``.
2. For each absorbed synth row, repoints its KI's ``xlm_ki_repo_link``
   rows to the canonical KI (de-duplicating if the canonical KI is
   already linked to the same repo, in which case the
   ``code_locations`` payload is merged).
3. Marks absorbed KIs ``is_active = False``.
4. Updates absorbed synth rows: ``merge_outcome = MERGED_INTO``,
   ``merged_into_id`` and ``knowledge_item_id`` repointed.

The production applier in ``mcp/handlers_feature_merge.py`` does
exactly this against the real tables — promotion is a name swap.
"""

import uuid
from dataclasses import dataclass
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from experiments.cross_layer_merge.schema import (
    XLMKnowledgeItem,
    XLMKnowledgeRepoLink,
    XLMMergeOutcome,
    XLMSynthesizedFeature,
)

log = structlog.get_logger(__name__)


@dataclass
class MergeResult:
    """Outcome surfaced back to the verifier for logging."""

    canonical_synth_id: uuid.UUID
    canonical_ki_id: uuid.UUID
    absorbed_synth_ids: list[uuid.UUID]
    absorbed_ki_ids: list[uuid.UUID]


async def apply_merge(
    *,
    canonical_synth_id: uuid.UUID,
    absorb_synth_ids: list[uuid.UUID],
) -> MergeResult:
    """Apply one merge plan atomically. Idempotent on already-merged rows."""
    if not absorb_synth_ids:
        raise ValueError("absorb_synth_ids must be non-empty")
    if canonical_synth_id in absorb_synth_ids:
        raise ValueError("canonical_synth_id cannot also appear in absorb_synth_ids")

    async with AsyncSessionLocal() as session:
        canonical_synth = await _require_synth(session, canonical_synth_id)
        if canonical_synth.knowledge_item_id is None:
            raise ValueError(
                f"canonical synth {canonical_synth_id} has no knowledge_item_id — "
                "must be CANONICAL with a promoted KI"
            )
        canonical_ki_id = canonical_synth.knowledge_item_id

        absorbed_ki_ids: list[uuid.UUID] = []
        for absorb_id in absorb_synth_ids:
            absorb_synth = await _require_synth(session, absorb_id)
            if absorb_synth.merge_outcome == XLMMergeOutcome.MERGED_INTO:
                # Already merged in a previous run — skip silently for idempotency.
                log.info("apply.skip_already_merged", synth_id=str(absorb_id))
                continue
            if absorb_synth.knowledge_item_id is None:
                log.warning("apply.absorb_no_ki", synth_id=str(absorb_id))
                continue

            absorbed_ki_id = absorb_synth.knowledge_item_id
            absorbed_ki_ids.append(absorbed_ki_id)

            await _repoint_repo_links(session, absorbed_ki_id, canonical_ki_id)
            await _deactivate_ki(session, absorbed_ki_id)

            absorb_synth.merge_outcome = XLMMergeOutcome.MERGED_INTO
            absorb_synth.merged_into_id = canonical_synth_id
            absorb_synth.knowledge_item_id = canonical_ki_id

        await session.commit()

    log.info(
        "apply.merge_done",
        canonical=str(canonical_synth_id),
        absorbed=[str(x) for x in absorb_synth_ids],
    )
    return MergeResult(
        canonical_synth_id=canonical_synth_id,
        canonical_ki_id=canonical_ki_id,
        absorbed_synth_ids=list(absorb_synth_ids),
        absorbed_ki_ids=absorbed_ki_ids,
    )


async def _require_synth(session: AsyncSession, synth_id: uuid.UUID) -> XLMSynthesizedFeature:
    row = await session.get(XLMSynthesizedFeature, synth_id)
    if row is None:
        raise LookupError(f"xlm_synth_feature row {synth_id} not found")
    return row


async def _repoint_repo_links(
    session: AsyncSession, absorbed_ki_id: uuid.UUID, canonical_ki_id: uuid.UUID
) -> None:
    """Move ``xlm_ki_repo_link`` rows from absorbed → canonical KI.

    If the canonical KI is already linked to the same repo, we keep
    the canonical link and merge ``code_locations`` rather than
    creating a duplicate (which would violate the implicit uniqueness
    on ``(knowledge_id, repo_id)`` in the production junction).
    """
    absorbed_links = (
        (
            await session.execute(
                select(XLMKnowledgeRepoLink).where(
                    XLMKnowledgeRepoLink.knowledge_id == absorbed_ki_id
                )
            )
        )
        .scalars()
        .all()
    )
    for link in absorbed_links:
        existing = (
            await session.execute(
                select(XLMKnowledgeRepoLink).where(
                    XLMKnowledgeRepoLink.knowledge_id == canonical_ki_id,
                    XLMKnowledgeRepoLink.repo_id == link.repo_id,
                )
            )
        ).scalar_one_or_none()

        if existing is None:
            link.knowledge_id = canonical_ki_id
        else:
            existing.code_locations = _merge_locations(
                existing.code_locations, link.code_locations
            )
            await session.delete(link)


def _merge_locations(
    left: dict[str, list[Any]] | None, right: dict[str, list[Any]] | None
) -> dict[str, list[Any]]:
    """Union the per-layer arrays in two ``code_locations`` payloads."""
    out: dict[str, list[Any]] = {}
    for src in (left or {}, right or {}):
        for layer, items in src.items():
            if layer not in out:
                out[layer] = []
            for item in items:
                if item not in out[layer]:
                    out[layer].append(item)
    return out


async def _deactivate_ki(session: AsyncSession, ki_id: uuid.UUID) -> None:
    ki = await session.get(XLMKnowledgeItem, ki_id)
    if ki is not None:
        ki.is_active = False
