# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Phase B3 — cross-repo feature merge: sole writer of canonical KIs.

Synthesis (B2) only stages rows in ``synthesized_features``. This
phase is the single place that creates canonical ``knowledge_items``
(category ``feature_registry``) and links them to repos via the
``knowledge_to_repo`` junction.

Branching:

- **0 NEW**: nothing to do (existing canonicals untouched).
- **1 NEW + 0 EXISTING**: deterministic copy; no Claude call.
  ``merge_writer.apply_single_feature_copy`` promotes the synth row.
- **otherwise**: build the two-section merge prompt, run Claude,
  apply ops via ``apply_feature_merge_plan``.

Post-merge sequence:

1. ``_promote_orphan_rows`` — best-effort fallback for any synth row
   Claude's cluster pass left unstamped (e.g., subprocess killed,
   plan covered only part of the cluster). Promotes via
   ``promote_synth_to_ki`` whose same-title attach folds duplicates
   into existing canonicals. Better than failing the whole scan over
   a 1-row gap.
2. ``_audit_strict`` — assertion that every NEW row now has an
   outcome. Anything still leftover here is a real logic bug; raise
   ``MergeIncompleteError`` so FEATURE_MERGE lands FAILED with
   ``error_code='merge_incomplete'``.
3. **Orphan-ratio gate** — if the fallback promoted ≥
   ``_ORPHAN_FAILURE_RATIO`` of this scan's rows, raise after
   committing the rescue. Preserves data while keeping the
   "Claude returned nothing" signal visible on the step row.
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization import Organization
from app.models.synthesized_feature import SynthesizedFeature
from app.repositories.knowledge_item import KnowledgeItemRepository
from app.repositories.organization import OrganizationRepository
from app.repositories.synthesized_feature import SynthesizedFeatureRepository
from app.repositories.tracked_repository import TrackedRepoRepository
from app.scan.prompts import build_merge_prompt
from app.services.claude_runner import (
    ClaudeRunnerConfig,
    MCPServerConfig,
    is_claude_cli_available,
    run_claude_code,
)
from app.services.feature_content import try_embed
from app.services.merge_writer import promote_synth_to_ki
from app.services.scan.phase_impls.feature_merge_cluster import cluster_for_merge
from app.services.scan.phase_impls.feature_merge_collect import (
    collect_feature_dicts,
    pick_merge_model,
)
from app.services.scan_checkpoints import MergeIncompleteError
from app.services.scan_helpers import embed_missing_items
from app.services.scan_progress import update_scan_progress

# ``app.services.scan_phases`` re-exports ``phase_b3_merge`` from this
# module to keep the orchestrator's import surface stable, which means
# we cannot import ``make_scan_progress_logger`` at module top without
# triggering a circular import. The runtime path uses a deferred
# import inside ``_run_llm_merge`` instead.

logger = structlog.get_logger(__name__)


# Source extensions worth showing the LLM when a repo has zero
# features — small enough to cap, broad enough to cover every web /
# mobile / backend stack we currently target. Kept in sync with
# ``app.services.platforms.*`` design extensions where it overlaps.
_SOURCE_EXTENSIONS = frozenset(
    {
        ".py",
        ".ts",
        ".tsx",
        ".js",
        ".jsx",
        ".vue",
        ".go",
        ".rs",
        ".java",
        ".kt",
        ".rb",
        ".cs",
        ".swift",
        ".svelte",
    }
)
_SKIP_DIRS = frozenset({".git", "node_modules", "dist", "__pycache__", ".next", "build"})


def _list_repo_files(repo_path: Path, max_files: int = 50) -> list[str]:
    """List source files in a repo (sync, for use in a thread).

    Filters to common source extensions and excludes build artifacts.
    """
    if not repo_path.exists():
        return []
    return [
        str(p.relative_to(repo_path))
        for p in sorted(repo_path.rglob("*"))
        if (
            p.is_file() and p.suffix in _SOURCE_EXTENSIONS and not _SKIP_DIRS.intersection(p.parts)
        )
    ][:max_files]


async def _collect_feature_dicts(
    db: AsyncSession,
    org_id: uuid.UUID,
    scan_uuid: uuid.UUID,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return ``(existing_canonicals, new_features)`` for the merge prompt.

    Thin wrapper around ``feature_merge_collect.collect_feature_dicts`` —
    kept here so callers that mock/patch the collector see a single
    boundary.
    """
    return await collect_feature_dicts(db, org_id, scan_uuid)


async def _find_repos_without_features(
    db: AsyncSession,
    org_id: uuid.UUID,
) -> list[dict]:
    """Find tracked repos that have no features linked to them.

    Returns their name + top-level file listing so the merge prompt
    can ask the LLM to link them to existing features.
    """
    tr_repo = TrackedRepoRepository(db, org_id=org_id)
    all_repos = await tr_repo.list_active()

    ki_repo = KnowledgeItemRepository(db, org_id=org_id)
    linked_repo_ids = await ki_repo.get_linked_repo_ids()

    result: list[dict] = []
    for repo in all_repos:
        if repo.id not in linked_repo_ids:
            rp = Path(repo.path)
            files = await asyncio.to_thread(_list_repo_files, rp)
            result.append({"name": repo.name, "files": files})
            logger.info(
                "repo_without_features",
                repo=repo.name,
                file_count=len(files),
            )
    return result


async def _resolve_org(db: AsyncSession, org_id: uuid.UUID) -> Organization:
    """Fetch the org row; raise if missing (the scan can't proceed)."""
    org_repo = OrganizationRepository(db)
    org = await org_repo.get_by_id(org_id)
    if org is None:
        raise RuntimeError(f"organization {org_id} not found during feature merge")
    return org


async def _run_llm_merge(
    *,
    db: AsyncSession,
    org_id: uuid.UUID,
    scan_id: str,
    repo_paths: list[str],
    scan_cfg: dict[str, Any],
    new_features: list[dict[str, Any]],
    existing_canonicals: list[dict[str, Any]],
    unlinked_repos: list[dict[str, Any]],
    cluster_index: int = 0,
    cluster_total: int = 1,
) -> None:
    """Build the merge prompt + run Claude. Raises on subprocess failure."""
    from app.config import settings as app_settings
    from app.mcp.auth import create_internal_mcp_token
    from app.services.org_settings import get_merge_models
    from app.services.scan.progress_logger import make_scan_progress_logger

    org_repo = OrganizationRepository(db)
    org_for_model = await org_repo.get_by_id(org_id)
    org_config_for_model = dict(org_for_model.config or {}) if org_for_model else {}
    default_model, large_model = get_merge_models(org_config_for_model)

    chosen_model = pick_merge_model(
        len(existing_canonicals) + len(new_features),
        default_model=default_model,
        large_model=large_model,
    )
    logger.info(
        "merge_model_selected",
        scan_id=scan_id,
        model=chosen_model,
        existing=len(existing_canonicals),
        new=len(new_features),
        cluster=f"{cluster_index + 1}/{cluster_total}",
    )

    await db.commit()

    merge_prompt = build_merge_prompt(
        new_features=new_features,
        existing_canonicals=existing_canonicals,
        unlinked_repos=unlinked_repos,
    )
    merge_token = create_internal_mcp_token(org_id)
    merge_cfg = ClaudeRunnerConfig(
        max_turns=scan_cfg.get("max_turns", 40),
        timeout_seconds=scan_cfg.get("merge_timeout_seconds", 300),
        output_format="json",
        model=chosen_model,
        mcp=MCPServerConfig(
            backend_url=app_settings.mcp_backend_url,
            mcp_token=merge_token,
        ),
        # Lock the merge subprocess to ONLY our MCP tool. Without this
        # Claude has Bash / Read / ToolSearch available and tends to
        # explore the codebase instead of emitting the merge plan we
        # asked for — burning the entire timeout on tool-use loops.
        allowed_tools=["mcp__bodhiorchard__apply_feature_merge_plan"],
    )
    result = await run_claude_code(
        prompt=merge_prompt,
        working_dir=str(Path(repo_paths[0]).parent),
        config=merge_cfg,
        progress_callback=make_scan_progress_logger(scan_id=scan_id, phase="feature_merge"),
    )
    if result.success:
        logger.info(
            "llm_merge_complete",
            new_count=len(new_features),
            existing_count=len(existing_canonicals),
            cost=result.cost_usd,
            cluster=f"{cluster_index + 1}/{cluster_total}",
        )
    else:
        logger.warning(
            "llm_merge_failed",
            error=result.error,
            cluster=f"{cluster_index + 1}/{cluster_total}",
        )


# Above this fraction of orphans, we still promote (preserves data) but
# raise MergeIncompleteError so the FEATURE_MERGE step lands FAILED.
# Tuned for "Claude returned an empty/incomplete plan" cases vs "one
# subprocess hiccup". 30% leans toward catching real breakage early —
# a single 50-row scan losing 15 rows is broken; losing 1-3 isn't.
_ORPHAN_FAILURE_RATIO = 0.30


async def _promote_orphan_rows(
    *,
    db: AsyncSession,
    org: Organization,
    scan_uuid: uuid.UUID,
) -> tuple[int, int]:
    """Best-effort promote any synth row Claude's cluster pass left unmerged.

    Reasons a row reaches here: Claude timed out before emitting a plan
    for the cluster, the plan covered some rows but not all, or a
    transient fault dropped the per-cluster write. ``promote_synth_to_ki``
    has same-title attach logic, so if a canonical with the same title
    already exists the row is linked as MERGED_INTO instead of creating
    a duplicate KI. Otherwise it lands as a fresh canonical — better
    than failing the entire scan over a 1-row gap.

    Returns:
        ``(orphan_count, scan_total)`` — caller uses the ratio to decide
        whether to raise after promoting (see ``_ORPHAN_FAILURE_RATIO``).
    """
    synth_repo = SynthesizedFeatureRepository(db, org_id=org.id)
    leftover = await synth_repo.list_unmerged_for_scan(scan_uuid)
    scan_total = await synth_repo.count_for_scan(scan_uuid)
    if not leftover:
        return 0, scan_total
    ratio = len(leftover) / scan_total if scan_total > 0 else 0.0
    logger.warning(
        "feature_merge_orphan_promote",
        scan_id=str(scan_uuid),
        count=len(leftover),
        scan_total=scan_total,
        ratio=round(ratio, 3),
        sample_ids=[str(r.id) for r in leftover[:5]],
    )
    for row in leftover:
        await promote_synth_to_ki(db=db, org=org, synth=row)
    await db.flush()
    return len(leftover), scan_total


async def _audit_strict(
    *,
    db: AsyncSession,
    org_id: uuid.UUID,
    scan_uuid: uuid.UUID,
) -> None:
    """Strict post-merge audit. Every NEW synth row must be stamped + linked.

    Runs *after* :func:`_promote_orphan_rows`, so any leftover here means
    even the fallback promote failed — a real bug worth surfacing.
    """
    synth_repo = SynthesizedFeatureRepository(db, org_id=org_id)
    leftover = await synth_repo.list_unmerged_for_scan(scan_uuid)
    if leftover:
        ids = sorted(str(row.id) for row in leftover)
        raise MergeIncompleteError(
            f"feature_merge left {len(leftover)} synth row(s) without an outcome "
            f"after orphan-promote fallback: {ids[:10]}{'…' if len(ids) > 10 else ''}"
        )


async def phase_b3_merge(
    db: AsyncSession,
    org_id: uuid.UUID,
    repo_paths: list[str],
    scan_cfg: dict[str, Any],
    scan_id: str,
    ki_repo: KnowledgeItemRepository,
) -> dict[str, Any]:
    """Phase B3: promote staged synth rows to canonical knowledge_items.

    Uses embedding-based clustering to send Claude focused dedup
    decisions instead of one giant 200+-feature prompt. Singletons
    (no related EXISTING canonicals) skip Claude entirely and go
    straight to ``promote_synth_to_ki``.
    """

    scan_uuid = uuid.UUID(scan_id)
    org = await _resolve_org(db, org_id)
    synth_repo = SynthesizedFeatureRepository(db, org_id=org_id)

    # Process the org's full unmerged set so stragglers from cancelled
    # / partially-completed prior scans get folded in. Audit-strict
    # below still scopes to ``scan_uuid`` because audit is per-scan.
    unmerged = await synth_repo.list_unmerged_org_wide()
    if not unmerged:
        logger.info("feature_merge_skip_no_new", scan_id=scan_id)
        return await _reload_org_config(db, org_id)

    await update_scan_progress(scan_id, status="merging_features", progress_pct=80)

    # 1. Lazy-fill embeddings for legacy rows. New rows already have
    #    them computed at synthesis write-time. After this one pass,
    #    every row in the unmerged set has an embedding cached.
    await _backfill_synth_embeddings(synth_repo, unmerged)
    await db.flush()

    # 2. Build clusters from synth-row + existing-canonical embeddings.
    existing_with_embedding = await ki_repo.list_active_features_with_embedding()
    clusters = cluster_for_merge(
        synth_rows=unmerged,
        existing_canonicals=existing_with_embedding,
    )

    # 3. Walk clusters: singletons skip Claude; multi-member or
    #    EXISTING-attached clusters get a focused Claude call.
    unlinked_repos = await _find_repos_without_features(db, org_id)
    new_lookup, existing_lookup = await _build_dict_lookups(db, org_id, scan_uuid)

    needs_claude = any(not c.is_singleton_with_no_existing_match for c in clusters)
    if needs_claude and not is_claude_cli_available():
        raise MergeIncompleteError(
            "Claude CLI is unavailable but cluster merge is required; "
            "install or repair the CLI and retry the FEATURE_MERGE phase."
        )

    for cluster_idx, cluster in enumerate(clusters):
        if cluster.is_singleton_with_no_existing_match:
            await promote_synth_to_ki(db=db, org=org, synth=cluster.synth_rows[0])
            await db.flush()
            continue

        cluster_new = [new_lookup[row.id] for row in cluster.synth_rows if row.id in new_lookup]
        cluster_existing = [
            existing_lookup[kid] for kid, _ in cluster.related_existing if kid in existing_lookup
        ]
        if not cluster_new:
            # Defensive: every cluster member should be in the NEW lookup.
            # If a row is missing it likely got promoted/absorbed by a prior
            # cluster — skip rather than bottoming out the LLM call.
            continue

        # Trivial-cluster fast path: title pre-clustering can union N
        # same-title synth rows into one cluster (e.g. "Authentication"
        # in 5 repos). The merge collector then dedupes by title, so
        # ``cluster_new`` ends up as 1 row. With 0 EXISTING canonicals
        # to compare against, Claude has no real decision to make —
        # promoting each synth row directly is faster and cheaper.
        # ``promote_synth_to_ki`` has a defensive same-title attach so
        # the second-and-later rows get linked as MERGED_INTO to the
        # first one's KI without a uniqueness violation.
        if len(cluster_new) <= 1 and not cluster_existing:
            for synth_row in cluster.synth_rows:
                await promote_synth_to_ki(db=db, org=org, synth=synth_row)
            await db.flush()
            continue

        await _run_llm_merge(
            db=db,
            org_id=org_id,
            scan_id=scan_id,
            repo_paths=repo_paths,
            scan_cfg=scan_cfg,
            new_features=cluster_new,
            existing_canonicals=cluster_existing,
            unlinked_repos=unlinked_repos if cluster_idx == 0 else [],
            cluster_index=cluster_idx,
            cluster_total=len(clusters),
        )
        await db.flush()

    orphan_count, scan_total = await _promote_orphan_rows(
        db=db, org=org, scan_uuid=scan_uuid
    )
    await _audit_strict(db=db, org_id=org_id, scan_uuid=scan_uuid)

    # Surface a high-orphan ratio as a hard failure so it shows up in the
    # FEATURE_MERGE step row + scan status, not just a warning log line.
    # We commit first so the promotes already done survive the raise —
    # ``with_session`` would otherwise rollback the orphan rescue work.
    if scan_total > 0 and orphan_count / scan_total >= _ORPHAN_FAILURE_RATIO:
        await db.commit()
        raise MergeIncompleteError(
            f"feature_merge orphan ratio {orphan_count / scan_total:.0%} exceeds "
            f"{_ORPHAN_FAILURE_RATIO:.0%} threshold ({orphan_count}/{scan_total} rows). "
            "Rows promoted as fallback; flagging as failed because Claude likely "
            "returned an empty or incomplete plan."
        )

    await embed_missing_items(db, org_id)
    return await _reload_org_config(db, org_id)


async def _backfill_synth_embeddings(
    synth_repo: SynthesizedFeatureRepository,
    rows: list[SynthesizedFeature],
) -> None:
    """Compute + persist embeddings for any synth rows still missing one.

    Legacy rows (pre-``zu_synth_feat_embedding``) have ``embedding=NULL``.
    The clusterer needs every vector before it can group, so we run a
    one-shot back-fill at the top of the merge phase. Mutates rows in
    place so the clusterer sees the freshly-computed values without a
    re-fetch.
    """
    missing = [r for r in rows if r.embedding is None]
    if not missing:
        return
    logger.info("feature_merge_embedding_backfill_start", count=len(missing))
    for row in missing:
        vec = await try_embed(row.feature_title, row.description)
        if vec is None:
            continue
        await synth_repo.set_embedding(row.id, vec)
        row.embedding = vec  # update in-memory copy for the clusterer
    logger.info("feature_merge_embedding_backfill_done", filled=len(missing))


async def _build_dict_lookups(
    db: AsyncSession,
    org_id: uuid.UUID,
    scan_uuid: uuid.UUID,
) -> tuple[dict[uuid.UUID, dict[str, Any]], dict[uuid.UUID, dict[str, Any]]]:
    """Build per-id dicts of NEW + EXISTING for cluster-scoped LLM calls.

    Reuses ``collect_feature_dicts`` to avoid divergence in the row
    shape consumed by ``build_merge_prompt``. Keys are UUIDs (not
    strings) so the cluster's ``synth_rows[i].id`` and
    ``related_existing[i][0]`` look up directly.
    """
    existing_list, new_list = await collect_feature_dicts(db, org_id, scan_uuid)
    new_by_id = {uuid.UUID(item["synth_id"]): item for item in new_list}
    existing_by_id = {uuid.UUID(item["knowledge_id"]): item for item in existing_list}
    return new_by_id, existing_by_id


async def _reload_org_config(db: AsyncSession, org_id: uuid.UUID) -> dict[str, Any]:
    """Re-read ``organizations.config`` after merge writes to surface any updates."""
    org_repo = OrganizationRepository(db)
    org = await org_repo.get_by_id(org_id)
    return dict(org.config or {}) if org else {}
