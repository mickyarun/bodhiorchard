# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""MCP-side helpers for maintaining the ``synthesized_features`` table.

The two MCP tools that write feature state (``write_feature_registry``
and ``merge_features``) call into this module so ``handlers_knowledge.py``
stays focused on its KnowledgeItem + KnowledgeRepoLink logic.

- ``persist_synth_feature`` is called during synthesis to append an
  immutable pre-merge row. It resolves the current scan_id from the
  in-flight scan state and supersedes prior rows for the same
  ``(repo, title)`` pair so the "latest" partial index stays clean.
- ``apply_merge_outcomes`` is called during merge to mark canonical and
  merged-into rows; the post-merge audit (``mark_canonical_for_active_kis``
  + ``mark_unvisited_for_inactive_kis``) lives in
  ``scan_phases.phase_b3_merge`` since it's a once-per-scan sweep, not
  a per-MCP-call concern.
"""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization import Organization
from app.models.scan_phase import MergeOutcome
from app.models.synthesized_feature import SynthesizedFeature
from app.repositories.synthesized_feature import SynthesizedFeatureRepository

logger = structlog.get_logger(__name__)


async def persist_synth_feature(
    *,
    db: AsyncSession,
    org: Organization,
    repo_id: uuid.UUID,
    feature_title: str,
    description: str,
    capabilities: list[str],
    cluster_names: list[str],
    code_locations: dict[str, list[str]] | None,
    knowledge_item_id: uuid.UUID | None,
) -> SynthesizedFeature | None:
    """Insert a ``synthesized_features`` row for the currently active scan.

    Resolves ``scan_id`` from the in-flight scan-progress state — if
    there is no active scan (e.g. a manual ``write_feature_registry``
    call outside a scan), returns ``None`` and skips the insert. The
    KnowledgeItem side of the tx is unaffected by this branch; this is
    a defensive guard for the edge case, not the hot path.

    Supersedes any prior ``(repo, title)`` row in the same transaction
    so the partial "latest" index (``superseded_at IS NULL``) always
    returns exactly one row per feature title per repo.
    """
    from app.services.scan_progress import get_active_scan_for_org

    active = await get_active_scan_for_org(str(org.id))
    if active is None:
        logger.warning(
            "synth_feature_skipped_no_active_scan",
            org_id=str(org.id),
            feature_title=feature_title,
        )
        return None

    scan_id = uuid.UUID(active.scan_id)
    synth_repo = SynthesizedFeatureRepository(db, org_id=org.id)

    # Mark any earlier row for this (repo, title) as superseded BEFORE
    # inserting the new one — the partial-unique invariant the downstream
    # queue self-heal depends on is one current row per (repo, title).
    await synth_repo.supersede_prior_by_title(
        repo_id=repo_id,
        feature_title=feature_title,
    )
    return await synth_repo.insert(
        scan_id=scan_id,
        repo_id=repo_id,
        feature_title=feature_title,
        description=description,
        capabilities={"capabilities": list(capabilities)},
        cluster_names=list(cluster_names),
        code_locations=dict(code_locations or {}),
        knowledge_item_id=knowledge_item_id,
    )


async def apply_merge_outcomes(
    *,
    db: AsyncSession,
    org: Organization,
    keep_title: str,
    merge_titles: list[str],
) -> tuple[int, int]:
    """Mark canonical and merged-into rows for a single ``merge_features`` call.

    Finds every current synth row for ``keep_title`` (there may be
    several — one per repo that synthesised the feature) and marks
    each as ``CANONICAL``. Then finds every current row for each title
    in ``merge_titles`` and marks them ``MERGED_INTO`` with
    ``merged_into_id`` pointing at the earliest canonical row.

    Returns:
        (canonical_count, merged_count) for logging.
    """
    synth_repo = SynthesizedFeatureRepository(db, org_id=org.id)

    canonical_rows = await synth_repo.find_current_by_title(keep_title)
    for row in canonical_rows:
        await synth_repo.mark_merge_outcome(row.id, MergeOutcome.CANONICAL)

    if not merge_titles or not canonical_rows:
        return len(canonical_rows), 0

    # Earliest canonical row is the audit target for all merged rows.
    # The order is stable because find_current_by_title orders by
    # ``synthesized_at ASC``.
    canonical_target_id = canonical_rows[0].id

    merged_count = 0
    for title in merge_titles:
        source_rows = await synth_repo.find_current_by_title(title)
        for row in source_rows:
            await synth_repo.mark_merge_outcome(
                row.id,
                MergeOutcome.MERGED_INTO,
                merged_into_id=canonical_target_id,
            )
            merged_count += 1

    return len(canonical_rows), merged_count
