# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""MCP-side helpers for maintaining the ``synthesized_features`` table.

The MCP tools that write feature state (``write_feature_registry``,
``apply_feature_merge_plan``) call into this module so the handler
modules stay focused on their KnowledgeItem + KnowledgeRepoLink logic.

- ``persist_synth_feature`` is called during synthesis to append an
  immutable pre-merge row. It resolves the current scan_id from the
  in-flight scan state and supersedes prior rows for the same
  ``(repo, title)`` pair so the "latest" partial index stays clean.
- ``apply_merge_outcomes_by_id`` is called during merge to mark
  canonical and merged-into rows; the post-merge audit
  (``mark_canonical_for_active_kis`` + ``mark_unvisited_for_inactive_kis``)
  lives in ``scan_phases.phase_b3_merge`` since it's a once-per-scan
  sweep, not a per-MCP-call concern.
"""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization import Organization
from app.models.scan_phase import MergeOutcome
from app.models.synthesized_feature import SynthesizedFeature
from app.repositories.synthesized_feature import SynthesizedFeatureRepository
from app.services.feature_content import try_embed

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
    tags: list[str] | None = None,
    scan_id: uuid.UUID | None = None,
) -> SynthesizedFeature | None:
    """Insert a ``synthesized_features`` row, binding it to a specific scan.

    ``scan_id`` is the authoritative way to route a write to its scan.
    The v2 synthesis prompt threads it through every Claude tool call
    so the persistence path doesn't have to guess. When the caller
    supplies ``scan_id`` it must reference an active (non-terminal)
    Scan row owned by ``org`` — invalid ids are rejected loudly rather
    than silently rerouted, so a hallucinated id can't write under the
    wrong scan.

    Legacy callers (``handlers_knowledge.py``) still omit ``scan_id``
    and fall back to ``get_active_scan_for_org`` so manual
    ``write_feature_registry`` calls outside a scan continue to work.

    Supersedes any prior ``(repo, title)`` row in the same transaction
    so the partial "latest" index (``superseded_at IS NULL``) always
    returns exactly one row per feature title per repo.
    """
    resolved_scan_id = await _resolve_scan_id(
        db=db,
        org=org,
        explicit_scan_id=scan_id,
        feature_title=feature_title,
    )
    if resolved_scan_id is None:
        return None

    synth_repo = SynthesizedFeatureRepository(db, org_id=org.id)

    # Mark any earlier row for this (repo, title) as superseded BEFORE
    # inserting the new one — the partial-unique invariant the downstream
    # queue self-heal depends on is one current row per (repo, title).
    await synth_repo.supersede_prior_by_title(
        repo_id=repo_id,
        feature_title=feature_title,
    )
    # Compute the embedding once at write-time. The merge phase clusters
    # by cosine similarity, so persisting the vector here saves
    # recomputing it on every merge sweep AND lets ``promote_synth_to_ki``
    # copy it forward instead of re-embedding the same content.
    # ``try_embed`` is fail-soft — returns None on any error, in which
    # case the merge phase will lazy-fill on its first encounter.
    embedding = await try_embed(feature_title, description)

    return await synth_repo.insert(
        scan_id=resolved_scan_id,
        repo_id=repo_id,
        feature_title=feature_title,
        description=description,
        capabilities={"capabilities": list(capabilities)},
        cluster_names=list(cluster_names),
        tags=list(tags or []),
        code_locations=dict(code_locations or {}),
        embedding=embedding,
        knowledge_item_id=knowledge_item_id,
    )


async def _resolve_scan_id(
    *,
    db: AsyncSession,
    org: Organization,
    explicit_scan_id: uuid.UUID | None,
    feature_title: str,
) -> uuid.UUID | None:
    """Pick the scan_id to bind this synth row to.

    Two paths:

    1. Caller supplied ``explicit_scan_id`` (v2 synth prompt). Validate
       the scan exists and belongs to this org, then accept it. We do
       NOT gate on scan status: a late MCP call landing after the
       orchestrator has already marked the scan terminal still
       represents a feature that was genuinely produced for that scan.
       Refusing it would throw away good audit data to enforce a
       constraint nobody asked for. Sequencing of the orchestrator vs.
       Claude's last MCP call is fixed in the runner (await_completion),
       not by this guard.
    2. Caller omitted it (legacy ``handlers_knowledge.py``). Use the
       global active-scan lookup as before, with the same logging on
       miss so the reason a write was skipped is visible in ops logs.
    """
    from app.models.scan import Scan

    if explicit_scan_id is not None:
        scan = await db.get(Scan, explicit_scan_id)
        if scan is None or scan.org_id != org.id:
            logger.error(
                "synth_feature_invalid_scan_id",
                org_id=str(org.id),
                scan_id=str(explicit_scan_id),
                feature_title=feature_title,
                hint="scan_id does not exist or belongs to a different org.",
            )
            return None
        return explicit_scan_id

    from app.services.scan_progress import get_active_scan_for_org

    active = await get_active_scan_for_org(str(org.id))
    if active is None:
        logger.error(
            "synth_feature_skipped_no_active_scan",
            org_id=str(org.id),
            feature_title=feature_title,
            hint=(
                "Legacy caller omitted scan_id and no active scan was "
                "found via scans.updated_at fallback. v2 callers should "
                "pass scan_id explicitly via the MCP tool params."
            ),
        )
        return None
    return uuid.UUID(active.scan_id)


async def apply_merge_outcomes_by_id(
    *,
    db: AsyncSession,
    org: Organization,
    canonical_knowledge_id: uuid.UUID,
    absorb_knowledge_ids: list[uuid.UUID],
) -> tuple[int, int]:
    """Mark canonical and merged-into rows for one ``apply_feature_merge_plan`` op.

    Stamps every current synth row whose ``knowledge_item_id`` matches
    ``canonical_knowledge_id`` as ``CANONICAL``, then stamps each
    ``absorb_knowledge_ids`` row as ``MERGED_INTO`` with
    ``merged_into_id`` pointing at the earliest canonical synth row.

    Args:
        canonical_knowledge_id: KI id of the surviving feature. All
            current synth rows whose ``knowledge_item_id`` matches are
            stamped ``CANONICAL``.
        absorb_knowledge_ids: KI ids whose synth rows should be
            stamped ``MERGED_INTO`` with ``merged_into_id`` pointing
            at the earliest canonical synth row.

    Returns:
        (canonical_count, merged_count) for logging.
    """
    synth_repo = SynthesizedFeatureRepository(db, org_id=org.id)

    canonical_rows = await synth_repo.find_current_by_knowledge_item_ids([canonical_knowledge_id])
    for row in canonical_rows:
        await synth_repo.mark_merge_outcome(row.id, MergeOutcome.CANONICAL)

    if not absorb_knowledge_ids or not canonical_rows:
        return len(canonical_rows), 0

    canonical_target_id = canonical_rows[0].id
    merged_count = 0
    absorb_rows = await synth_repo.find_current_by_knowledge_item_ids(absorb_knowledge_ids)
    for row in absorb_rows:
        await synth_repo.mark_merge_outcome(
            row.id,
            MergeOutcome.MERGED_INTO,
            merged_into_id=canonical_target_id,
        )
        merged_count += 1

    return len(canonical_rows), merged_count
