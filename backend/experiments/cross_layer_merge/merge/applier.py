# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Cluster-merge applier — mirrors ``merge_writer._absorb_synth_rows`` shape.

Different from ``apply.merge_applier.apply_merge`` (the pair-verifier
applier): that one assumes both canonical and absorb synth rows are
already promoted to canonical KIs and deactivates the absorb's KI
when folding. This applier is for the **cluster-merge runner**, where:

- The canonical synth row has been promoted (has ``knowledge_item_id``).
- The absorb synth rows have NOT been promoted (``knowledge_item_id``
  is None — they never had their own KI to begin with).

For each absorb row we:

1. Link the canonical's KI to the absorb's repo (idempotent — re-run
   safe). Carries the absorb's ``code_locations`` payload through.
2. Back-fill ``absorb.knowledge_item_id = canonical_ki_id``.
3. Stamp ``merge_outcome = MERGED_INTO`` and ``merged_into_id =
   canonical_synth_id``.

No KI deactivation happens here because the absorbs never had their
own. This is exactly how production's
``app.services.merge_writer._absorb_synth_rows`` consolidates NEW
synth rows into a canonical that the merge phase just promoted.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from experiments.cross_layer_merge.merge.promote import _ensure_link
from experiments.cross_layer_merge.schema import (
    XLMMergeOutcome,
    XLMSynthesizedFeature,
)

log = structlog.get_logger(__name__)


@dataclass
class ClusterMergeResult:
    """Counters surfaced back to the runner for telemetry."""

    canonical_synth_id: uuid.UUID
    canonical_ki_id: uuid.UUID
    absorbed_synth_ids: list[uuid.UUID]


async def apply_cluster_merge(
    *,
    canonical_synth_id: uuid.UUID,
    absorb_synth_ids: list[uuid.UUID],
) -> ClusterMergeResult:
    """Fold a list of absorb synth rows into a canonical synth's KI.

    Idempotent on already-merged rows — running twice is safe.
    Caller is responsible for ensuring the canonical has been promoted
    (``knowledge_item_id`` non-null) before this call.
    """
    if not absorb_synth_ids:
        raise ValueError("absorb_synth_ids must be non-empty")
    if canonical_synth_id in absorb_synth_ids:
        raise ValueError("canonical_synth_id cannot also appear in absorb_synth_ids")

    async with AsyncSessionLocal() as session:
        canonical = await _require_synth(session, canonical_synth_id)
        if canonical.knowledge_item_id is None:
            raise ValueError(
                f"canonical synth {canonical_synth_id} has no knowledge_item_id — "
                "promote_synth_to_ki must run before apply_cluster_merge"
            )
        canonical_ki_id = canonical.knowledge_item_id

        absorbed: list[uuid.UUID] = []
        for absorb_id in absorb_synth_ids:
            absorb = await _require_synth(session, absorb_id)
            if absorb.merge_outcome == XLMMergeOutcome.MERGED_INTO:
                # Already folded in a previous run — skip silently for idempotency.
                log.info("applier.skip_already_merged", synth_id=str(absorb_id))
                continue

            await _ensure_link(
                session,
                canonical_ki_id,
                absorb.repo_id,
                absorb.code_locations or None,
            )
            absorb.knowledge_item_id = canonical_ki_id
            absorb.merge_outcome = XLMMergeOutcome.MERGED_INTO
            absorb.merged_into_id = canonical_synth_id
            absorbed.append(absorb_id)

        await session.commit()

    log.info(
        "applier.cluster_merge_done",
        canonical=str(canonical_synth_id),
        absorbed=[str(x) for x in absorbed],
    )
    return ClusterMergeResult(
        canonical_synth_id=canonical_synth_id,
        canonical_ki_id=canonical_ki_id,
        absorbed_synth_ids=absorbed,
    )


async def _require_synth(session: AsyncSession, synth_id: uuid.UUID) -> XLMSynthesizedFeature:
    row = await session.get(XLMSynthesizedFeature, synth_id)
    if row is None:
        raise LookupError(f"xlm_synth_feature row {synth_id} not found")
    return row
