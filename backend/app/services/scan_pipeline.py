"""Background scan pipeline orchestrator.

Coordinates all scan phases (A→G): change detection, GitNexus indexing,
feature synthesis via Claude Code, cross-repo merge, skill analysis,
embedding generation, and config persistence.

Phase implementations live in ``scan_phases.py``; reusable helpers
(timing, upsert, embedding) live in ``scan_helpers.py``.
"""

import uuid
from pathlib import Path

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.knowledge_item import KnowledgeItemRepository
from app.repositories.organization import OrganizationRepository
from app.repositories.user import UserRepository
from app.schemas.skills import ScanStatus
from app.services.claude_runner import is_claude_cli_available
from app.services.git_analyzer import analyze_repo_skills, get_head_sha
from app.services.git_operations import create_scan_worktree, remove_scan_worktree
from app.services.gitnexus_indexer import GitNexusNotInstalledError, index_repo_with_gitnexus
from app.services.scan_helpers import (
    PhaseTimer,
    cleanup_stale_references,
    embed_missing_items,
    load_feature_map,
)
from app.services.scan_phases import (
    phase_a_scan_mode,
    phase_b1_repo_setup,
    phase_b2_synthesis,
    phase_b3_merge,
    phase_e2_skill_remap,
    phase_e_skills,
    phase_g_persist,
)

logger = structlog.get_logger(__name__)

# If >30% of tracked files changed, fall back to full scan
INCREMENTAL_THRESHOLD = 0.30

# Max features per LLM merge call (configurable via LLM_MERGE_BATCH_SIZE env)
def get_merge_batch_size() -> int:
    """Return the max features per LLM merge call from config."""
    from app.config import settings

    return settings.llm.merge_batch_size

# In-memory scan status tracking (use Redis in production)
scan_statuses: dict[str, ScanStatus] = {}


def _publish_scan_status(scan_id: str, scan_status: ScanStatus) -> None:
    """Publish scan status to the event bus for WebSocket delivery."""
    from app.services.event_bus import publish

    publish(f"scan:{scan_id}", scan_status.model_dump(by_alias=True))


def build_synthesis_prompt(
    repo_name: str,
    readme_overview: str,
    is_workspace: bool,
) -> str:
    """Build the Claude Code prompt for feature synthesis.

    Args:
        repo_name: Name of the repository being processed.
        readme_overview: First 2000 chars of the repo README.
        is_workspace: Whether this is a multi-repo workspace scan.

    Returns:
        Prompt string for Claude Code CLI.
    """
    repo_name_line = f'      - repo_name: "{repo_name}"'
    return f"""You are synthesizing human-readable feature descriptions \
for repository "{repo_name}".

README Overview:
{readme_overview[:2000]}

## Instructions

Follow this loop exactly:

1. Call `get_pending_features` to get the next batch of unprocessed clusters
2. If the response has `done: true`, you are finished — stop here
3. For each cluster in the batch:
   a. Read the cluster's key files to understand what the code does
   b. Skip infrastructure/utility clusters (logging, config, migrations, CI/CD)
   c. For real business features, call `write_feature_registry` with:
      - feature_name: Human-readable name (e.g., "Card Payments")
      - description: 1-2 sentences of what this feature does in business terms
      - capabilities: 3-6 specific things this feature does
      - code_locations: Map layers to file paths, e.g.:
        {{"backend": ["src/services/card/"], "frontend": ["src/views/Pay.vue"]}}
        Layers: backend, frontend, batch (background jobs), other
      - tags: 2-5 lowercase search keywords
      - source_clusters: Array containing the cluster name(s)
{repo_name_line}
4. Go back to step 1

## Grouping Rules

- Group related functionality into a SINGLE feature. For example, all
  OTP-related code (verification, generation, recovery) should be ONE
  feature called "OTP Authentication", not separate features per sub-function.
- When multiple clusters clearly belong to the same domain, combine them
  into one `write_feature_registry` call with all their code_locations merged.
- Target 8-15 features per repo. Prefer broader domain-level features
  over narrow per-function features.

Important: Process ALL clusters returned by get_pending_features before calling
it again. Do not call get_pending_features mid-batch."""


def build_merge_prompt(
    features: list[dict],
    unlinked_repos: list[dict] | None = None,
) -> str:
    """Build a prompt for cross-repo feature merging.

    Lists all features with their repo names and tags. The LLM calls
    ``merge_features`` for groups that represent the same business
    capability across repos.

    Also lists repos whose code wasn't clustered (e.g. small frontend
    repos) so the LLM can link them to existing features by name.

    Args:
        features: List of dicts with keys: title, repo_names, tags.
        unlinked_repos: Repos with 0 clusters — include their file
            listing so the LLM can link them to features.

    Returns:
        Prompt string for Claude Code CLI.
    """
    lines = []
    for i, f in enumerate(features, 1):
        repos = ", ".join(f["repo_names"]) if f["repo_names"] else "unlinked"
        tags = ", ".join(f.get("tags") or [])
        lines.append(f'{i}. "{f["title"]}" ({repos}) — {tags}')

    feature_list = "\n".join(lines)

    unlinked_section = ""
    if unlinked_repos:
        repo_lines = []
        for repo in unlinked_repos:
            files = ", ".join(repo["files"][:20])
            repo_lines.append(f'- **{repo["name"]}**: {files}')
        unlinked_section = f"""

## Repos with no features yet

These repos were scanned but produced no features (too small for clustering).
Link them to existing features if their code matches:

{chr(10).join(repo_lines)}
"""

    return f"""You are merging duplicate features across repositories.

## Features

{feature_list}
{unlinked_section}
## Instructions

1. Look for features that represent the SAME business capability but exist
   in different repos (or have slightly different names). Call `merge_features`
   to consolidate them.

2. For repos listed under "Repos with no features yet", if their files clearly
   belong to an existing feature (e.g. a frontend repo with auth views matches
   "Authentication"), call `merge_features` with that repo added to repo_names.

Parameters for merge_features:
- keep_title: The most descriptive title from the group (exact match required)
- merge_titles: The other titles to merge into it (will be deactivated)
- repo_names: ALL repository names this feature belongs to

Rules:
- Only merge features that are clearly the same domain
- Do NOT merge features that are merely related (e.g. "Billing" and "Payments" are separate)
- If no duplicates or links exist, you are done — do nothing"""


async def _maybe_extract_design_system(
    db: AsyncSession,
    org_id: uuid.UUID,
    repo_path: str,
    tracked_repo: object | None,
    full_rescan: bool,
) -> None:
    """Auto-extract design system during scan if design files are detected.

    Runs the extractor inline (not as a separate job) and upserts the result.
    Skips if the source files haven't changed since last extraction (by hash),
    unless full_rescan is True.

    The first repo with a design system is set as the org default if none exists.

    Args:
        db: Async database session.
        org_id: Organization UUID.
        repo_path: Absolute path to the repository.
        tracked_repo: TrackedRepository model instance (or None).
        full_rescan: Whether this is a full rescan (force re-extraction).
    """
    from datetime import UTC, datetime

    from app.repositories.design_system import DesignSystemRefRepository
    from app.services.design_system_extractor import (
        compute_hash,
        discover_design_files,
        extract_design_system,
        read_discovered_files,
    )
    from app.services.repo_setup import detect_repo_type

    if detect_repo_type(repo_path) != "frontend":
        logger.debug("design_system_skip_non_frontend", repo=Path(repo_path).name)
        return

    repo = Path(repo_path)
    discovered = discover_design_files(repo)
    if not discovered:
        return  # No design files — skip silently

    repo_id = tracked_repo.id if tracked_repo and hasattr(tracked_repo, "id") else None
    if repo_id is None:
        return

    # Check if source files changed since last extraction (skip if unchanged)
    file_contents = read_discovered_files(discovered)
    source_hash = compute_hash(file_contents)

    ds_repo = DesignSystemRefRepository(db, org_id=org_id)
    existing = await ds_repo.get_for_repo(repo_id)

    if existing and existing.source_hash == source_hash and not full_rescan:
        logger.info(
            "design_system_unchanged",
            repo=repo.name,
            hash=source_hash[:12],
        )
        return

    logger.info(
        "design_system_auto_extracting",
        repo=repo.name,
        file_count=len(discovered),
    )

    extraction = await extract_design_system(repo)

    # Set as org default if no default exists yet
    is_default = False
    existing_default = await ds_repo.get_default()
    if existing_default is None:
        is_default = True

    await ds_repo.upsert(
        repo_id=repo_id,
        content=extraction.content,
        source_hash=extraction.source_hash,
        extracted_at=datetime.now(UTC),
        is_default=is_default,
    )
    await db.flush()

    logger.info(
        "design_system_auto_extracted",
        repo=repo.name,
        method=extraction.method,
        is_default=is_default,
        error=extraction.error,
    )


async def run_scan_pipeline(
    scan_id: str,
    org_id: uuid.UUID,
    repo_paths: list[str],
    full_rescan: bool,
    user_id: str | None = None,
) -> None:
    """Execute the scan pipeline as a background task.

    Supports both single-repo and workspace (multi-repo) modes.
    For workspaces, each repo is scanned sequentially and results are aggregated.

    Phases per repo:
        A. Determine scan mode (incremental vs full)
        B. GitNexus indexing → knowledge_items (clusters)
        B1. Worktrees, MCP init, hooks, .gitignore, commit+push+PR
        D. Stale reference cleanup (incremental only)
        E. Git skill analysis → skill_profiles
        E1b. Auto-extract design system (if design files detected)
    Then globally:
        B2. Feature synthesis via Claude Code
        E2. Re-run skill analysis with feature-based modules
        B3. Cross-repo feature merge (workspace only)
        F. Embedding generation for items missing embeddings
        G. Save last_commit_sha per repo to org config

    Args:
        scan_id: Unique scan identifier for status tracking.
        org_id: Organization UUID.
        repo_paths: List of absolute paths to git repositories to scan.
        full_rescan: Whether to force a complete rescan.
        user_id: Optional user ID for sending completion notifications.
    """
    from app.database import AsyncSessionLocal

    scan_status = scan_statuses[scan_id]
    is_workspace = len(repo_paths) > 1
    timer = PhaseTimer(scan_id)
    soft_deleted_ids: list[uuid.UUID] = []

    try:
        async with AsyncSessionLocal() as db:
            org_repo = OrganizationRepository(db)
            org = await org_repo.get_by_id(org_id)
            config = dict(org.config or {})
            scan_cfg = config.get("scan", {})

            total_features_synthesized = 0
            total_profiles = 0
            _pending_synthesis: list[dict] = []
            total_stale = 0
            all_unmatched: list[str] = []
            overall_mode = "full"
            new_shas: dict[str, str] = {}

            user_repo = UserRepository(db)
            email_to_user = await user_repo.get_email_map(org_id)

            # Load tracked repo records for SHA lookup and post-scan updates
            from app.repositories.tracked_repository import TrackedRepoRepository

            tracked_repo_repo = TrackedRepoRepository(db, org_id=org_id)

            # On full scan, soft-delete old scan-sourced features (preserves
            # data for rollback if the pipeline fails partway through).
            ki_repo = KnowledgeItemRepository(db, org_id=org_id)
            if full_rescan or not config.get("knowledge", {}).get("last_commit_sha"):
                soft_deleted_ids = await ki_repo.soft_delete_by_category_excluding_source(
                    "feature_registry", exclude_source="bud"
                )
                await db.flush()
                if soft_deleted_ids:
                    logger.info(
                        "scan_soft_deleted_features",
                        scan_id=scan_id,
                        deactivated=len(soft_deleted_ids),
                    )

            for repo_idx, repo_path in enumerate(repo_paths):
                repo_name = Path(repo_path).name
                base_pct = int(5 + (repo_idx / len(repo_paths)) * 80)
                repo_pct_range = 80 // len(repo_paths)

                if is_workspace:
                    logger.info(
                        "scan_workspace_repo",
                        scan_id=scan_id,
                        repo=repo_name,
                        index=repo_idx + 1,
                        total=len(repo_paths),
                    )

                tracked_repo = await tracked_repo_repo.get_by_path(repo_path)
                main_branch = (tracked_repo.main_branch if tracked_repo else None) or "main"

                # Create a temporary worktree for scanning the main branch
                # without touching the user's working tree.
                try:
                    scan_path = await create_scan_worktree(repo_path, main_branch)
                except RuntimeError:
                    logger.warning(
                        "scan_worktree_failed_using_repo",
                        scan_id=scan_id,
                        repo=repo_name,
                    )
                    scan_path = repo_path  # Fallback: scan in-place

                try:
                    # --- Phase A: Determine scan mode ---
                    timer.start()
                    scan_status.status = "analyzing_changes"
                    scan_status.progress_pct = base_pct
                    _publish_scan_status(scan_id, scan_status)

                    last_sha = tracked_repo.head_sha if tracked_repo else None
                    if not last_sha:
                        knowledge_cfg = config.get("knowledge") or {}
                        last_sha = knowledge_cfg.get("repo_shas", {}).get(
                            repo_path
                        ) or knowledge_cfg.get("last_commit_sha")

                    # Per-repo copy so one repo forcing full_rescan doesn't
                    # leak to subsequent repos (Bug 1 fix).
                    repo_full_rescan = full_rescan
                    is_incremental, repo_full_rescan, deleted_files = await phase_a_scan_mode(
                        db,
                        org_id,
                        repo_path,
                        repo_name,
                        repo_full_rescan,
                        last_sha,
                        ki_repo,
                        scan_id,
                    )
                    if is_incremental:
                        overall_mode = "incremental"

                    timer.mark(f"A_scan_mode/{repo_name}")

                    # --- Phase B: GitNexus indexing ---
                    timer.start()
                    scan_status.status = "indexing"
                    scan_status.progress_pct = base_pct + int(repo_pct_range * 0.1)
                    _publish_scan_status(scan_id, scan_status)

                    gitnexus_result = await index_repo_with_gitnexus(
                        scan_path,
                        force=not is_incremental,
                    )

                    if gitnexus_result.success:
                        from app.services.claude_runner import ensure_gitnexus_mcp

                        await ensure_gitnexus_mcp()

                    await db.flush()
                    timer.mark(f"B_gitnexus/{repo_name}")

                    # --- Phase B1: Worktrees, MCP init, hooks, .gitignore ---
                    timer.start()
                    await phase_b1_repo_setup(
                        db,
                        org_id,
                        repo_path,
                        repo_name,
                        tracked_repo,
                        scan_id,
                        scan_status,
                    )
                    timer.mark(f"B1_repo_setup/{repo_name}")

                    # --- Collect Phase B2 synthesis task ---
                    if (
                        not is_incremental
                        and gitnexus_result.success
                        and gitnexus_result.features
                        and is_claude_cli_available()
                    ):
                        from app.mcp.server import set_synthesis_queue

                        # Adaptive threshold: small repos (< 10 clusters) use
                        # lower bar so nothing is lost; large repos filter noise.
                        total_clusters = len(gitnexus_result.features)
                        min_files = 2 if total_clusters < 10 else 3
                        queue_items = [
                            {
                                "name": f.name,
                                "files": f.files[:15],
                                "symbols": len(f.files),
                                "repo_name": repo_name,
                            }
                            for f in gitnexus_result.features
                            if len(f.files) >= min_files
                        ]
                        queue_key = set_synthesis_queue(
                            str(org_id),
                            queue_items,
                            repo_name=repo_name,
                        )
                        _pending_synthesis.append(
                            {
                                "repo_name": repo_name,
                                "repo_path": repo_path,
                                "overview": gitnexus_result.repo_overview or "",
                                "queue_key": queue_key,
                                "cluster_count": len(queue_items),
                            }
                        )
                    elif not is_incremental and not is_claude_cli_available():
                        logger.info("feature_synthesis_skipped_no_claude_cli")

                    # --- Phase D: Stale reference cleanup (incremental only) ---
                    timer.start()
                    if is_incremental and deleted_files:
                        scan_status.status = "cleaning_stale"
                        cleaned = await cleanup_stale_references(db, org_id, deleted_files)
                        total_stale += cleaned
                        await db.flush()

                    timer.mark(f"D_stale_cleanup/{repo_name}")

                    # --- Phase E: Git skill analysis ---
                    timer.start()
                    scan_status.status = "analyzing_skills"
                    scan_status.progress_pct = base_pct + int(repo_pct_range * 0.6)
                    _publish_scan_status(scan_id, scan_status)

                    feature_map = await load_feature_map(db, org_id)
                    skill_entries = await analyze_repo_skills(
                        scan_path, feature_map=feature_map or None
                    )

                    profiles, unmatched, email_to_user = await phase_e_skills(
                        db,
                        org_id,
                        repo_path,
                        skill_entries,
                        email_to_user,
                        scan_cfg,
                    )
                    total_profiles += profiles
                    all_unmatched.extend(u for u in unmatched if u not in all_unmatched)

                    timer.mark(f"E_skills/{repo_name}")

                    # --- Phase E1b: Auto-extract design system ---
                    timer.start()
                    try:
                        await _maybe_extract_design_system(
                            db,
                            org_id,
                            scan_path,
                            tracked_repo,
                            repo_full_rescan,
                        )
                    except Exception:
                        logger.exception(
                            "design_system_auto_extract_failed",
                            scan_id=scan_id,
                            repo=repo_name,
                        )
                    timer.mark(f"E1b_design_system/{repo_name}")

                    # Track HEAD SHA per repo (use scan_path for accurate SHA)
                    head_sha = await get_head_sha(scan_path)
                    if head_sha:
                        new_shas[repo_path] = head_sha

                finally:
                    await remove_scan_worktree(repo_path)

            # --- Phase B2: Parallel feature synthesis via Claude Code ---
            timer.start()
            total_features_synthesized = await phase_b2_synthesis(
                db,
                org_id,
                _pending_synthesis,
                is_workspace,
                scan_cfg,
                scan_status,
                ki_repo,
            )
            timer.mark("B2_synthesis_parallel")

            # --- Phase B3: Cross-repo merge + embedding + dedup ---
            # Must run BEFORE E2 so skill remap uses merged feature names.
            timer.start()
            merge_config = await phase_b3_merge(
                db,
                org_id,
                repo_paths,
                is_workspace,
                total_features_synthesized,
                scan_cfg,
                scan_status,
                ki_repo,
            )
            if merge_config:
                config = merge_config
            timer.mark("B3_merge")

            # --- Phase E2: Re-run skill analysis with merged feature names ---
            if _pending_synthesis and total_features_synthesized > 0:
                timer.start()
                e2_profiles = await phase_e2_skill_remap(
                    db,
                    org_id,
                    repo_paths,
                    email_to_user,
                    scan_status,
                )
                if e2_profiles:
                    total_profiles = e2_profiles
                timer.mark("E2_skill_remap")

            # Synthesis + merge succeeded — hard-delete only the features that
            # were soft-deleted at scan start and not reactivated by synthesis.
            if soft_deleted_ids:
                purged = await ki_repo.delete_inactive_by_ids(soft_deleted_ids)
                if purged:
                    await db.flush()
                    logger.info("scan_purged_stale_features", scan_id=scan_id, purged=purged)

            # --- Phase G: Save last commit SHAs + scan results ---
            timer.start()
            actual_features = await phase_g_persist(
                db,
                org_id,
                repo_paths,
                new_shas,
                config,
                total_profiles,
                all_unmatched,
                overall_mode,
                ki_repo,
            )
            timer.mark("G_persist")

            # Final catch-all: embed any items still missing embeddings
            # (e.g. created during merge after the earlier embed pass).
            final_embedded = await embed_missing_items(db, org_id)
            if final_embedded:
                logger.info("scan_final_embed_pass", scan_id=scan_id, embedded=final_embedded)

            scan_status.features_indexed = actual_features
            scan_status.profiles_found = total_profiles
            scan_status.stale_cleaned = total_stale
            scan_status.unmatched_authors = all_unmatched[:20]
            scan_status.scan_mode = overall_mode
            scan_status.status = "completed"
            scan_status.progress_pct = 100
            _publish_scan_status(scan_id, scan_status)

            logger.info(
                "scan_complete",
                scan_id=scan_id,
                repos=len(repo_paths),
                mode=overall_mode,
                features=actual_features,
                profiles=total_profiles,
                unmatched=len(all_unmatched),
                phase_timings=timer.timings,
            )

            if user_id:
                from app.services.notification_service import send_scan_notification

                send_scan_notification(
                    scan_id=scan_id,
                    user_id=user_id,
                    org_id=str(org_id),
                    completed=True,
                    features_indexed=actual_features,
                    profiles_found=total_profiles,
                )

    except GitNexusNotInstalledError as exc:
        logger.error("scan_gitnexus_not_installed", scan_id=scan_id, error=str(exc))
        scan_status.status = "failed"
        scan_status.error = str(exc)
        _publish_scan_status(scan_id, scan_status)
        await _rollback_soft_deleted_features(org_id, scan_id, soft_deleted_ids)
        if user_id:
            from app.services.notification_service import send_scan_notification

            send_scan_notification(
                scan_id=scan_id,
                user_id=user_id,
                org_id=str(org_id),
                completed=False,
                error_message=str(exc),
            )
    except Exception as exc:
        logger.exception("scan_pipeline_error", scan_id=scan_id)
        scan_status.status = "failed"
        scan_status.error = str(exc)[:500]
        _publish_scan_status(scan_id, scan_status)
        await _rollback_soft_deleted_features(org_id, scan_id, soft_deleted_ids)
        if user_id:
            from app.services.notification_service import send_scan_notification

            send_scan_notification(
                scan_id=scan_id,
                user_id=user_id,
                org_id=str(org_id),
                completed=False,
                error_message=str(exc)[:500],
            )


async def _rollback_soft_deleted_features(
    org_id: uuid.UUID,
    scan_id: str,
    deactivated_ids: list[uuid.UUID],
) -> None:
    """Reactivate only the features soft-deleted by this scan run.

    Uses a fresh DB session since the original session may be in a bad state.

    Args:
        org_id: Organization UUID.
        scan_id: Scan identifier for logging.
        deactivated_ids: IDs of items soft-deleted at scan start.
    """
    if not deactivated_ids:
        return

    from app.database import AsyncSessionLocal

    try:
        async with AsyncSessionLocal() as recovery_db:
            ki_recovery = KnowledgeItemRepository(recovery_db, org_id=org_id)
            restored = await ki_recovery.reactivate_by_ids(deactivated_ids)
            await recovery_db.commit()
            if restored:
                logger.info(
                    "scan_rollback_restored_features",
                    scan_id=scan_id,
                    restored=restored,
                )
    except Exception:
        logger.exception("scan_rollback_failed", scan_id=scan_id)
