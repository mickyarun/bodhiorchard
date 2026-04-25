# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Phase B3 — cross-repo feature merge via Claude + post-merge audit.

Three logical stages, all sequential:

1. **Embedding backfill** for any newly-synthesised features (so the
   merge prompt's similarity hints work).
2. **Multi-pass Claude merge.** Up to 3 passes over batches of ~32
   features, asking Claude to call ``merge_features(keep_title=…,
   merge_titles=[…])`` whenever it spots cross-repo duplicates. Bails
   out early when a pass produces zero merges.
3. **Post-merge audit (two-tier).** Every ``synthesized_features`` row
   whose ``merge_outcome`` is still NULL gets classified:
   - KI still active → CANONICAL (Claude saw it, judged unique).
   - KI inactive / missing → UNVISITED (raise ``MergeIncompleteError``).

Until the two-tier audit shipped, every unique feature flagged the
whole scan as ``merge_incomplete`` because Claude rationally never
called ``merge_features`` on a feature with no duplicates. That
cascade prevented SKILL_REMAP from running and left the Skills view
stuck on directory modules.
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

import structlog
from sqlalchemy import select as sa_select
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.knowledge_item import KnowledgeItemRepository
from app.services.claude_runner import (
    ClaudeRunnerConfig,
    MCPServerConfig,
    is_claude_cli_available,
    run_claude_code,
)
from app.services.feature_merger import dedup_merged_features
from app.services.scan_helpers import embed_missing_items

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
) -> list[dict]:
    """Collect active features with their repo names for the merge prompt.

    Uses a single joined query to avoid N+1. Returns only features
    that are linked to at least one repo (orphans are excluded).
    """
    from app.models.knowledge_item import KnowledgeItem, KnowledgeRepoLink
    from app.models.tracked_repository import TrackedRepository

    rows = (
        await db.execute(
            sa_select(
                KnowledgeItem.title,
                KnowledgeItem.tags,
                TrackedRepository.name.label("repo_name"),
            )
            .outerjoin(KnowledgeRepoLink, KnowledgeRepoLink.knowledge_id == KnowledgeItem.id)
            .outerjoin(TrackedRepository, TrackedRepository.id == KnowledgeRepoLink.repo_id)
            .where(
                KnowledgeItem.org_id == org_id,
                KnowledgeItem.category == "feature_registry",
                KnowledgeItem.is_active.is_(True),
            )
        )
    ).all()

    grouped: dict[str, dict] = {}
    for title, tags, repo_name in rows:
        if title not in grouped:
            grouped[title] = {"title": title, "repo_names": [], "tags": tags or []}
        if repo_name and repo_name not in grouped[title]["repo_names"]:
            grouped[title]["repo_names"].append(repo_name)

    return [f for f in grouped.values() if f["repo_names"]]


async def _find_repos_without_features(
    db: AsyncSession,
    org_id: uuid.UUID,
) -> list[dict]:
    """Find tracked repos that have no features linked to them.

    Returns their name + top-level file listing so the merge prompt
    can ask the LLM to link them to existing features.
    """
    from app.models.knowledge_item import KnowledgeItem, KnowledgeRepoLink
    from app.repositories.tracked_repository import TrackedRepoRepository

    tr_repo = TrackedRepoRepository(db, org_id=org_id)
    all_repos = await tr_repo.list_active()

    linked_repo_ids = set(
        (
            await db.execute(
                sa_select(KnowledgeRepoLink.repo_id)
                .distinct()
                .join(KnowledgeItem, KnowledgeItem.id == KnowledgeRepoLink.knowledge_id)
                .where(KnowledgeItem.org_id == org_id)
            )
        )
        .scalars()
        .all()
    )

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


async def phase_b3_merge(
    db: AsyncSession,
    org_id: uuid.UUID,
    repo_paths: list[str],
    is_workspace: bool,
    total_features_synthesized: int,
    scan_cfg: dict,
    scan_id: str,
    ki_repo: KnowledgeItemRepository,
) -> dict:
    """Phase B3: Cross-repo feature merge via LLM + embedding + cleanup.

    Lists all features for the LLM, which calls ``merge_features`` MCP
    to consolidate duplicates across repos. Replaces the old semantic
    dedup approach.

    Args:
        db: Async database session.
        org_id: Organization UUID.
        repo_paths: List of all repo paths being scanned.
        is_workspace: Whether this is a multi-repo workspace scan.
        total_features_synthesized: Count of features from synthesis.
        scan_cfg: Scan configuration dict from org config.
        scan_id: Scan identifier for progress tracking.
        ki_repo: Knowledge item repository instance.

    Returns:
        Dict with possibly updated ``config`` (after commit/reload).
    """
    from app.repositories.organization import OrganizationRepository
    from app.repositories.synthesized_feature import SynthesizedFeatureRepository
    from app.services.scan_checkpoints import MergeIncompleteError
    from app.services.scan_helpers import link_orphan_features
    from app.services.scan_phases import make_scan_progress_logger
    from app.services.scan_pipeline import build_merge_prompt, get_merge_batch_size
    from app.services.scan_progress import update_scan_progress

    await update_scan_progress(scan_id, status="generating_embeddings", progress_pct=80)
    await embed_missing_items(db, org_id)

    config: dict = {}
    if is_workspace and total_features_synthesized >= 2 and is_claude_cli_available():
        await update_scan_progress(scan_id, status="merging_features", progress_pct=88)

        linked_features = await _collect_feature_dicts(db, org_id)
        unlinked_repos = await _find_repos_without_features(db, org_id)

        if linked_features:
            await db.commit()

            from app.config import settings
            from app.mcp.auth import create_internal_mcp_token

            merge_batch_size = get_merge_batch_size()
            prev_count = await ki_repo.count_active(category="feature_registry")
            for _pass in range(3):  # Re-run if batch < total (cross-batch dupes)
                for batch_start in range(0, len(linked_features), merge_batch_size):
                    batch = linked_features[batch_start : batch_start + merge_batch_size]
                    merge_prompt = build_merge_prompt(batch, unlinked_repos=unlinked_repos)

                    merge_token = create_internal_mcp_token(org_id)
                    merge_cfg = ClaudeRunnerConfig(
                        max_turns=scan_cfg.get("max_turns", 40),
                        timeout_seconds=scan_cfg.get("timeout_seconds", 300),
                        output_format="json",
                        model=settings.llm.merge_model,
                        mcp=MCPServerConfig(
                            backend_url=settings.mcp_backend_url,
                            mcp_token=merge_token,
                        ),
                    )
                    result = await run_claude_code(
                        prompt=merge_prompt,
                        working_dir=str(Path(repo_paths[0]).parent),
                        config=merge_cfg,
                        progress_callback=make_scan_progress_logger(
                            scan_id=scan_id,
                            phase="feature_merge",
                        ),
                    )
                    if result.success:
                        logger.info(
                            "llm_merge_complete",
                            pass_num=_pass + 1,
                            batch_size=len(batch),
                            cost=result.cost_usd,
                        )
                    else:
                        logger.warning("llm_merge_failed", error=result.error)

                new_count = await ki_repo.count_active(category="feature_registry")
                if new_count >= prev_count:
                    break  # No merges — done
                prev_count = new_count

                linked_features = await _collect_feature_dicts(db, org_id)

            await embed_missing_items(db, org_id)

            org_repo = OrganizationRepository(db)
            org = await org_repo.get_by_id(org_id)
            config = dict(org.config or {})

    deduped = await dedup_merged_features(db, org_id)
    if deduped:
        logger.info("post_merge_dedup", deactivated=deduped)

    cleanup_deleted = await ki_repo.delete_inactive_by_category("feature_registry")
    if cleanup_deleted:
        await db.flush()
        logger.info("merge_artifact_cleanup", deleted=cleanup_deleted)

    await link_orphan_features(db, org_id, ki_repo)

    # Post-merge audit (two-tier).
    #
    # NULL ``merge_outcome`` rows split into two cases:
    #   1. KI still active → Claude saw the feature in the prompt and
    #      rationally judged "no duplicate to merge into". Mark it
    #      CANONICAL — the steady-state for a unique feature.
    #   2. KI inactive / missing → genuine partial-merge signal. Raise
    #      ``MergeIncompleteError`` so the FEATURE_MERGE checkpoint
    #      lands FAILED with ``error_code='merge_incomplete'``.
    #
    # Order matters: canonical-flip first so unvisited-flip's
    # ``merge_outcome IS NULL`` predicate sees only the orphans.
    synth_repo = SynthesizedFeatureRepository(db, org_id=org_id)
    canonical_marked = await synth_repo.mark_canonical_for_active_kis()
    unvisited = await synth_repo.mark_unvisited_for_inactive_kis()
    await db.flush()
    if canonical_marked:
        logger.info("merge_audit_canonical_default", scan_id=scan_id, count=canonical_marked)
    if unvisited:
        logger.warning("merge_audit_unvisited", scan_id=scan_id, unvisited_count=unvisited)
        raise MergeIncompleteError(
            f"Merge completed but {unvisited} feature(s) have inactive "
            "knowledge_items without a merge target; retry the "
            "FEATURE_MERGE phase to consolidate them."
        )

    return config
