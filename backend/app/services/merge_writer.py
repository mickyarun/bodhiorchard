# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Promote ``synthesized_features`` rows to ``knowledge_items``.

The merge phase is the sole writer of canonical ``knowledge_items``
(category=``feature_registry``). Per-repo synthesis only stages rows in
``synthesized_features``; this module turns those staged rows into the
post-merge canonical view consumed by the UI and downstream agents.

Three entry points:

- :func:`promote_synth_to_ki` — create a fresh KI from one synth row,
  link the junction, back-fill ``knowledge_item_id`` on the synth row,
  stamp ``merge_outcome=CANONICAL``.
- :func:`apply_single_feature_copy` — fast path used when the scan
  produced exactly one synth row and there are zero existing
  canonicals. No LLM call needed.
- :func:`apply_merge_op` — execute one structured op from
  ``apply_feature_merge_plan``: resolve canonical (NEW synth or
  EXISTING KI), apply absorbs (synth + KI), link extra repos.
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge_item import KnowledgeItem
from app.models.organization import Organization
from app.models.scan_phase import MergeOutcome
from app.models.synthesized_feature import SynthesizedFeature
from app.repositories.knowledge_item import KnowledgeItemRepository
from app.repositories.synthesized_feature import SynthesizedFeatureRepository
from app.services.feature_content import format_feature_content, try_embed

logger = structlog.get_logger(__name__)


def _capabilities_list(synth: SynthesizedFeature) -> list[str]:
    """Pull the flat capabilities list from a synth row's JSONB column."""
    raw = (synth.capabilities or {}).get("capabilities")
    if not isinstance(raw, list):
        return []
    return [str(c) for c in raw if c]


async def promote_synth_to_ki(
    *,
    db: AsyncSession,
    org: Organization,
    synth: SynthesizedFeature,
) -> KnowledgeItem:
    """Create or attach to a canonical ``knowledge_item`` from a synth row.

    If an active feature_registry KI with the same title already
    exists, attach the synth row to it as MERGED_INTO instead of
    creating a duplicate (which would violate the
    ``uq_ki_org_title_feature_active`` constraint). This handles the
    cross-repo case where two synth rows have identical titles but
    embeddings just below the clustering threshold.

    Otherwise inserts a fresh KI, links the junction with the synth
    row's ``code_locations``, back-fills ``synth.knowledge_item_id``,
    and stamps ``merge_outcome=CANONICAL``. Caller controls
    transaction boundaries.
    """
    ki_repo = KnowledgeItemRepository(db, org_id=org.id)
    synth_repo = SynthesizedFeatureRepository(db, org_id=org.id)

    # Defensive: attach to an existing same-title KI before trying to
    # insert a fresh one. Catches the edge case where the clusterer
    # missed grouping two same-title rows because their descriptions
    # diverged just below the cosine threshold.
    existing = await ki_repo.get_by_title_and_category(synth.feature_title, "feature_registry")
    if existing is not None:
        code_locations = synth.code_locations or None
        await ki_repo.link_to_repo(existing.id, synth.repo_id, code_locations=code_locations)
        await ki_repo.flush()
        await synth_repo.back_fill_knowledge_item_id(synth.id, existing.id)
        await synth_repo.mark_merge_outcome(
            synth.id,
            MergeOutcome.MERGED_INTO,
            merged_into_id=None,
        )
        logger.info(
            "merge_writer_attach_existing",
            synth_id=str(synth.id),
            ki_id=str(existing.id),
            title=synth.feature_title,
        )
        return existing

    capabilities = _capabilities_list(synth)
    cluster_names = list(synth.cluster_names or [])
    synth_tags = list(synth.tags or [])
    # Tags Claude emitted at synthesis time win; fall back to cluster
    # names so older synth rows (pre-tags-column) still produce a usable
    # tag set on the canonical KI.
    ki_tags = (synth_tags or cluster_names)[:10] or None
    content = format_feature_content(
        description=synth.description,
        capabilities=capabilities,
        source_clusters=cluster_names,
        feature_status="implemented",
    )
    # Copy the synth row's embedding (computed at synthesis write-time)
    # instead of recomputing here. The fallback ``try_embed`` only fires
    # for legacy synth rows that pre-date the embedding column.
    embedding = synth.embedding
    if embedding is None:
        embedding = await try_embed(synth.feature_title, content)
    item = KnowledgeItem(
        org_id=org.id,
        category="feature_registry",
        title=synth.feature_title,
        content=content,
        source="scan",
        tags=ki_tags,
        is_active=True,
        feature_status="implemented",
        embedding=embedding,
    )
    await ki_repo.add(item)
    await ki_repo.flush()

    code_locations = synth.code_locations or None
    await ki_repo.link_to_repo(item.id, synth.repo_id, code_locations=code_locations)
    await ki_repo.flush()

    await synth_repo.back_fill_knowledge_item_id(synth.id, item.id)
    await synth_repo.mark_merge_outcome(synth.id, MergeOutcome.CANONICAL)
    return item


async def apply_single_feature_copy(
    *,
    db: AsyncSession,
    org: Organization,
) -> KnowledgeItem | None:
    """Deterministic fast path for the 1-NEW + 0-EXISTING case.

    Skips the LLM merge entirely when the org has exactly one unmerged
    synth row and zero existing canonicals (the merge phase's caller
    is responsible for verifying the EXISTING side is empty).
    """
    synth_repo = SynthesizedFeatureRepository(db, org_id=org.id)
    rows = await synth_repo.list_unmerged_org_wide()
    if len(rows) != 1:
        raise ValueError(
            f"apply_single_feature_copy requires exactly 1 unmerged synth row, "
            f"found {len(rows)} org-wide"
        )
    return await promote_synth_to_ki(db=db, org=org, synth=rows[0])


async def _resolve_canonical(
    *,
    db: AsyncSession,
    org: Organization,
    canonical_synth_id: uuid.UUID | None,
    canonical_knowledge_id: uuid.UUID | None,
    ki_map: dict[uuid.UUID, KnowledgeItem],
) -> tuple[uuid.UUID, uuid.UUID | None]:
    """Pin down the canonical KI id (creating one from synth if needed).

    Returns ``(canonical_ki_id, canonical_synth_id_or_none)``. The synth
    id is ``None`` when the canonical is an EXISTING KI without a
    current synth row — absorbed rows then get
    ``merged_into_id=NULL`` (relaxed invariant).
    """
    if canonical_synth_id is not None:
        synth_repo = SynthesizedFeatureRepository(db, org_id=org.id)
        synth = await synth_repo.get_by_id(canonical_synth_id)
        if synth is None:
            raise ValueError(f"unknown canonical_synth_id: {canonical_synth_id}")
        if synth.knowledge_item_id is None:
            ki = await promote_synth_to_ki(db=db, org=org, synth=synth)
            return ki.id, synth.id
        return synth.knowledge_item_id, synth.id

    assert canonical_knowledge_id is not None, "_resolve_canonical: one of the two ids is required"
    canonical_ki = ki_map.get(canonical_knowledge_id)
    if canonical_ki is None:
        raise ValueError(f"unknown canonical_knowledge_id: {canonical_knowledge_id}")

    synth_repo = SynthesizedFeatureRepository(db, org_id=org.id)
    matching = await synth_repo.find_current_by_knowledge_item_ids([canonical_knowledge_id])
    canonical_synth_id_resolved = matching[0].id if matching else None
    return canonical_ki.id, canonical_synth_id_resolved


async def _absorb_synth_rows(
    *,
    db: AsyncSession,
    org: Organization,
    absorb_synth_ids: list[uuid.UUID],
    canonical_ki_id: uuid.UUID,
    canonical_synth_id: uuid.UUID | None,
) -> None:
    """Stamp NEW synth rows as MERGED_INTO and attach their repos to the canonical."""
    if not absorb_synth_ids:
        return
    synth_repo = SynthesizedFeatureRepository(db, org_id=org.id)
    ki_repo = KnowledgeItemRepository(db, org_id=org.id)

    for sid in absorb_synth_ids:
        synth = await synth_repo.get_by_id(sid)
        if synth is None:
            raise ValueError(f"unknown absorb_synth_id: {sid}")
        await ki_repo.link_to_repo(
            canonical_ki_id, synth.repo_id, code_locations=synth.code_locations or None
        )
        await synth_repo.back_fill_knowledge_item_id(sid, canonical_ki_id)
        await synth_repo.mark_merge_outcome(
            sid,
            MergeOutcome.MERGED_INTO,
            merged_into_id=canonical_synth_id,
        )


async def _absorb_existing_kis(
    *,
    db: AsyncSession,
    org: Organization,
    absorb_knowledge_ids: list[uuid.UUID],
    canonical_ki_id: uuid.UUID,
    canonical_synth_id: uuid.UUID | None,
    ki_map: dict[uuid.UUID, KnowledgeItem],
) -> int:
    """Transfer junctions + deactivate absorbed EXISTING KIs; stamp their synth rows.

    Returns the count of KIs deactivated for telemetry.
    """
    active = [aid for aid in absorb_knowledge_ids if ki_map[aid].is_active]
    if not active:
        return 0
    ki_repo = KnowledgeItemRepository(db, org_id=org.id)
    synth_repo = SynthesizedFeatureRepository(db, org_id=org.id)

    await ki_repo.transfer_repo_links(active, canonical_ki_id)
    deactivated = await ki_repo.bulk_deactivate_by_ids(active)
    await ki_repo.flush()

    related = await synth_repo.find_current_by_knowledge_item_ids(active)
    for row in related:
        await synth_repo.back_fill_knowledge_item_id(row.id, canonical_ki_id)
        await synth_repo.mark_merge_outcome(
            row.id,
            MergeOutcome.MERGED_INTO,
            merged_into_id=canonical_synth_id,
        )
    return deactivated


async def apply_merge_op(
    *,
    db: AsyncSession,
    org: Organization,
    op: dict[str, Any],
    ki_map: dict[uuid.UUID, KnowledgeItem],
) -> dict[str, int]:
    """Execute one merge op. Caller handles transaction + ki_map prefetch.

    ``op`` must have already been shape-validated by the MCP handler.
    """
    canonical_ki_id, canonical_synth_id = await _resolve_canonical(
        db=db,
        org=org,
        canonical_synth_id=op.get("canonical_synth_id"),
        canonical_knowledge_id=op.get("canonical_knowledge_id"),
        ki_map=ki_map,
    )

    await _absorb_synth_rows(
        db=db,
        org=org,
        absorb_synth_ids=op.get("absorb_synth_ids") or [],
        canonical_ki_id=canonical_ki_id,
        canonical_synth_id=canonical_synth_id,
    )

    deactivated = await _absorb_existing_kis(
        db=db,
        org=org,
        absorb_knowledge_ids=op.get("absorb_knowledge_ids") or [],
        canonical_ki_id=canonical_ki_id,
        canonical_synth_id=canonical_synth_id,
        ki_map=ki_map,
    )

    repo_ids = op.get("repo_ids") or []
    if repo_ids:
        ki_repo = KnowledgeItemRepository(db, org_id=org.id)
        await ki_repo.link_to_repos(canonical_ki_id, repo_ids)

    return {
        "merged_features": deactivated,
        "repo_links_added": len(repo_ids),
    }
