"""Background scan pipeline orchestrator.

Coordinates all scan phases (A→G): change detection, GitNexus indexing,
feature synthesis via Claude Code, cross-repo merge, skill analysis,
embedding generation, and config persistence.
"""

import time
import uuid
from pathlib import Path

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.skill_profile import SkillProfile
from app.models.user import User
from app.repositories.knowledge_item import KnowledgeItemRepository
from app.repositories.organization import OrganizationRepository
from app.repositories.skill_profile import SkillProfileRepository
from app.repositories.user import UserRepository
from app.schemas.skills import ScanStatus
from app.services.claude_runner import (
    ClaudeRunnerConfig,
    MCPServerConfig,
    is_claude_cli_available,
    run_claude_code,
)
from app.services.embedding_service import embedding_service
from app.services.feature_merger import (
    build_targeted_merge_prompt,
    deactivate_superseded_repo_features,
    dedup_merged_features,
    find_semantic_duplicates,
    merge_same_name_features,
)
from app.services.git_analyzer import FeatureMap, analyze_repo_skills, get_diff_since, get_head_sha
from app.services.repo_scanner import (
    GitNexusNotInstalledError,
    add_bodhigrove_gitignore,
    add_prepare_script,
    commit_and_push_bodhigrove_setup,
    ensure_repo_worktrees,
    index_repo_with_gitnexus,
    init_bodhigrove_mcp_in_repo,
    install_hooks,
)

logger = structlog.get_logger(__name__)

# If >30% of tracked files changed, fall back to full scan
INCREMENTAL_THRESHOLD = 0.30

# In-memory scan status tracking (use Redis in production)
scan_statuses: dict[str, ScanStatus] = {}


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
    repo_name_line = f'      - repo_name: "{repo_name}"' if is_workspace else ""
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

Important: Process ALL clusters returned by get_pending_features before calling
it again. Do not call get_pending_features mid-batch."""


async def _cleanup_stale_references(
    db: AsyncSession,
    org_id: uuid.UUID,
    deleted_files: list[str],
) -> int:
    """Deactivate knowledge items whose source_ref matches a deleted file.

    Items are soft-deleted (is_active=False) so they can be recovered.

    Args:
        db: The async database session.
        org_id: Organization UUID.
        deleted_files: List of deleted file paths.

    Returns:
        Number of items deactivated.
    """
    if not deleted_files:
        return 0

    ki_repo = KnowledgeItemRepository(db, org_id=org_id)
    items = await ki_repo.list_active_items()

    deactivated = 0
    deleted_set = set(deleted_files)

    for item in items:
        if item.source_ref and item.source_ref in deleted_set:
            item.is_active = False
            item.embedding = None
            deactivated += 1

    logger.info(
        "stale_cleanup",
        org_id=str(org_id),
        deleted_files=len(deleted_files),
        deactivated=deactivated,
    )
    return deactivated


async def _embed_missing_items(db: AsyncSession, org_id: uuid.UUID) -> int:
    """Embed all knowledge items that are missing embeddings.

    Processes in batches of 20 to avoid overloading the embedding service.

    Args:
        db: The async database session.
        org_id: Organization UUID.

    Returns:
        Number of items embedded.
    """
    ki_repo = KnowledgeItemRepository(db, org_id=org_id)
    items = await ki_repo.list_missing_embeddings()

    if not items:
        return 0

    batch_size = 20
    total_embedded = 0

    for i in range(0, len(items), batch_size):
        batch = items[i : i + batch_size]
        texts = [f"{item.title}\n{item.content or ''}"[:2000] for item in batch]

        try:
            vectors = await embedding_service.embed_batch(texts)
            for item, vector in zip(batch, vectors, strict=True):
                item.embedding = vector
            total_embedded += len(batch)
            await db.flush()
        except Exception:
            logger.exception("embed_batch_failed", batch_start=i, batch_size=len(batch))
            break

    logger.info("embed_missing_items", org_id=str(org_id), embedded=total_embedded)
    return total_embedded


async def _load_feature_map(db: AsyncSession, org_id: uuid.UUID) -> FeatureMap:
    """Load (feature_name, flattened_path_list, feature_id) from active features.

    Strips title prefixes (``[Repo] Feature:`` or ``Feature:``) to produce
    clean names for skill profiles.  Sorts by path length descending so
    longest-prefix matching works correctly.

    Args:
        db: The async database session.
        org_id: Organization UUID.

    Returns:
        List of (feature_name, [path_prefixes], knowledge_item_id) tuples.
    """
    import re

    ki_repo = KnowledgeItemRepository(db, org_id=org_id)
    items = await ki_repo.list_active(category="feature_registry", limit=500)

    prefix_re = re.compile(r"^(?:\[[^\]]+\]\s*)?Feature:\s*")
    result: FeatureMap = []

    for item in items:
        if not item.code_locations:
            continue
        # Clean feature name
        name = prefix_re.sub("", item.title).strip()
        if not name:
            continue
        # Flatten all layer paths into one list
        all_paths: list[str] = []
        for paths in item.code_locations.values():
            if isinstance(paths, list):
                all_paths.extend(paths)
        if all_paths:
            result.append((name, all_paths, item.id))

    # Sort by longest path first for greedy matching
    result.sort(key=lambda entry: max((len(p) for p in entry[1]), default=0), reverse=True)
    return result


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
    from app.services.repo_scanner import detect_repo_type

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
        B2. Feature synthesis via Claude Code → feature_registry items
        C. Documentation extraction → knowledge_items
        D. Stale reference cleanup (incremental only)
        E. Git skill analysis → skill_profiles
        E1b. Auto-extract design system (if design files detected)
    Then globally:
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
    pipeline_t0 = time.monotonic()
    phase_timings: dict[str, float] = {}

    def _mark(phase: str, t0: float) -> None:
        elapsed = round(time.monotonic() - t0, 1)
        phase_timings[phase] = elapsed
        logger.info("scan_phase_done", scan_id=scan_id, phase=phase, elapsed_s=elapsed)

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

            # On full scan, delete old scan-sourced feature items up front
            # (BUD-sourced items are preserved — they represent user intent)
            ki_repo = KnowledgeItemRepository(db, org_id=org_id)
            if full_rescan or not config.get("knowledge", {}).get("last_commit_sha"):
                deleted_count = await ki_repo.delete_by_category_excluding_source(
                    "feature_registry", exclude_source="bud"
                )
                await db.flush()
                if deleted_count:
                    logger.info(
                        "scan_deleted_old_features",
                        scan_id=scan_id,
                        deleted=deleted_count,
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

                # --- Phase A: Determine scan mode ---
                phase_t0 = time.monotonic()
                scan_status.status = "analyzing_changes"
                scan_status.progress_pct = base_pct

                # Look up last SHA from tracked_repositories table
                tracked_repo = await tracked_repo_repo.get_by_path(repo_path)
                last_sha = tracked_repo.head_sha if tracked_repo else None
                # Fallback to legacy config for repos not yet in the table
                if not last_sha:
                    knowledge_cfg = config.get("knowledge") or {}
                    last_sha = knowledge_cfg.get("repo_shas", {}).get(
                        repo_path
                    ) or knowledge_cfg.get("last_commit_sha")
                is_incremental = False
                deleted_files: list[str] = []

                # Check if we have any scan-sourced features — if not, force full scan
                # even if last_sha exists (e.g. after code rewrite that changed scanner logic)
                if not full_rescan and last_sha:
                    has_scan_features = await ki_repo.has_any(source="scan")
                    if not has_scan_features:
                        logger.info(
                            "scan_force_full_no_scan_features",
                            scan_id=scan_id,
                            repo=repo_name,
                        )
                        full_rescan = True

                if not full_rescan and last_sha:
                    diff = await get_diff_since(repo_path, last_sha)
                    total_changed = len(diff.changed_files) + len(diff.deleted_files)

                    if diff.total_repo_files > 0:
                        change_ratio = total_changed / diff.total_repo_files
                    else:
                        change_ratio = 1.0

                    if change_ratio <= INCREMENTAL_THRESHOLD and total_changed > 0:
                        is_incremental = True
                        deleted_files = diff.deleted_files
                    elif total_changed == 0:
                        is_incremental = True
                    else:
                        logger.info(
                            "scan_full_threshold_exceeded",
                            scan_id=scan_id,
                            repo=repo_name,
                            ratio=round(change_ratio, 3),
                        )
                else:
                    logger.info(
                        "scan_full",
                        scan_id=scan_id,
                        repo=repo_name,
                        reason="first_run" if not last_sha else "forced",
                    )

                if is_incremental:
                    overall_mode = "incremental"

                _mark(f"A_scan_mode/{repo_name}", phase_t0)

                # --- Phase B: GitNexus indexing ---
                phase_t0 = time.monotonic()
                scan_status.status = "indexing"
                scan_status.progress_pct = base_pct + int(repo_pct_range * 0.1)

                gitnexus_result = await index_repo_with_gitnexus(
                    repo_path,
                    force=not is_incremental,
                )

                # Register GitNexus MCP with Claude Code (idempotent, ~1s if already done)
                if gitnexus_result.success:
                    from app.services.claude_runner import ensure_gitnexus_mcp

                    await ensure_gitnexus_mcp()

                await db.flush()
                _mark(f"B_gitnexus/{repo_name}", phase_t0)

                # --- Phase B1: Worktrees, MCP init, hooks, .gitignore ---
                # Each function is idempotent — skips if already configured.
                # Committable files (.claude/settings.json, .gitignore) are
                # committed back to the repo so all devs get them on pull.
                phase_t0 = time.monotonic()
                try:
                    main_wt, develop_wt = await ensure_repo_worktrees(repo_path)

                    # Persist detected branches to tracked_repositories
                    if tracked_repo:
                        from app.services.repo_scanner import (
                            _detect_develop_branch,
                            _detect_main_branch,
                        )

                        if tracked_repo.main_branch is None:
                            detected_main = await _detect_main_branch(repo_path)
                            if detected_main:
                                tracked_repo.main_branch = detected_main
                        if tracked_repo.develop_branch is None:
                            detected_dev = await _detect_develop_branch(repo_path)
                            if detected_dev:
                                tracked_repo.develop_branch = detected_dev

                    # Init Bodhigrove MCP in repo (skips if already configured)
                    from app.config import settings as app_settings
                    from app.mcp.auth import create_internal_mcp_token

                    mcp_token = create_internal_mcp_token(org_id)
                    mcp_changed = await init_bodhigrove_mcp_in_repo(
                        repo_path, app_settings.public_url, mcp_token
                    )

                    # Install git hooks to .githooks/ (committed) + set core.hooksPath
                    hooks_changed = await install_hooks(
                        repo_path, app_settings.public_url, str(org_id)
                    )

                    # Add .bodhigrove/ to .gitignore (skips if already present)
                    gitignore_changed = add_bodhigrove_gitignore(repo_path)

                    # Add prepare script to package.json (auto-sets hooksPath on npm install)
                    prepare_changed = add_prepare_script(repo_path)

                    # Branch, commit, and push setup files for team review
                    any_changed = (
                        mcp_changed or hooks_changed or gitignore_changed or prepare_changed
                    )
                    if any_changed:
                        base = (
                            tracked_repo.main_branch
                            if tracked_repo and tracked_repo.main_branch
                            else "main"
                        )
                        pushed_branch = await commit_and_push_bodhigrove_setup(repo_path, base)
                        if pushed_branch:
                            logger.info(
                                "bodhigrove_setup_branch_pushed",
                                repo=repo_name,
                                branch=pushed_branch,
                            )

                    await db.flush()
                except Exception:
                    logger.exception(
                        "scan_repo_setup_failed",
                        scan_id=scan_id,
                        repo=repo_name,
                    )
                _mark(f"B1_repo_setup/{repo_name}", phase_t0)

                # --- Collect Phase B2 synthesis task (run in parallel later) ---
                if (
                    not is_incremental
                    and gitnexus_result.success
                    and gitnexus_result.features
                    and is_claude_cli_available()
                ):
                    from app.mcp.server import set_synthesis_queue

                    queue_items = [
                        {
                            "name": f.name,
                            "files": f.files[:15],
                            "symbols": len(f.files),
                            "repo_name": repo_name if is_workspace else None,
                        }
                        for f in gitnexus_result.features
                        if len(f.files) >= 3  # skip tiny clusters
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

                # Phase C (documentation extraction) removed — agents use
                # the Read tool to access docs directly from the repo.

                # --- Phase D: Stale reference cleanup (incremental only) ---
                phase_t0 = time.monotonic()
                if is_incremental and deleted_files:
                    scan_status.status = "cleaning_stale"
                    cleaned = await _cleanup_stale_references(db, org_id, deleted_files)
                    total_stale += cleaned
                    await db.flush()

                _mark(f"D_stale_cleanup/{repo_name}", phase_t0)

                # --- Phase E: Git skill analysis ---
                phase_t0 = time.monotonic()
                scan_status.status = "analyzing_skills"
                scan_status.progress_pct = base_pct + int(repo_pct_range * 0.6)

                # Load feature map for feature-linked skill profiles
                # (on incremental scans, features already exist from prior full scan)
                feature_map = await _load_feature_map(db, org_id)
                skill_entries = await analyze_repo_skills(
                    repo_path, feature_map=feature_map or None
                )

                # Auto-create members from git authors if enabled
                auto_create = scan_cfg.get("auto_create_members", True)
                if auto_create and skill_entries:
                    # Refresh map to catch users created by earlier repos
                    email_to_user = await user_repo.get_email_map(org_id)
                    seen_emails: set[str] = set()
                    for entry in skill_entries:
                        email_lower = entry.email.lower()
                        if email_lower in email_to_user or email_lower in seen_emails:
                            continue
                        seen_emails.add(email_lower)
                        new_user = User(
                            org_id=org_id,
                            email=entry.email,
                            name=entry.author_name,
                            password_hash=hash_password("changeme123"),
                            is_active=True,
                        )
                        db.add(new_user)
                    await db.flush()
                    email_to_user = await user_repo.get_email_map(org_id)

                sp_repo = SkillProfileRepository(db, org_id=org_id)
                for entry in skill_entries:
                    user = email_to_user.get(entry.email.lower())
                    if user is None:
                        if entry.email not in all_unmatched:
                            all_unmatched.append(entry.email)
                        continue

                    total_profiles += 1
                    profile = await sp_repo.get_by_user_and_module(user.id, entry.module)

                    if profile:
                        profile.touch_count = entry.touch_count
                        profile.skill_score = entry.skill_score
                        profile.languages = entry.languages
                        profile.last_touch = entry.last_touch
                        profile.feature_id = entry.feature_id
                    else:
                        profile = SkillProfile(
                            user_id=user.id,
                            org_id=org_id,
                            module=entry.module,
                            feature_id=entry.feature_id,
                            repo=repo_path,
                            languages=entry.languages,
                            skill_score=entry.skill_score,
                            touch_count=entry.touch_count,
                            last_touch=entry.last_touch,
                        )
                        db.add(profile)

                await db.flush()

                _mark(f"E_skills/{repo_name}", phase_t0)

                # --- Phase E1b: Auto-extract design system (if design files exist) ---
                phase_t0 = time.monotonic()
                try:
                    await _maybe_extract_design_system(
                        db,
                        org_id,
                        repo_path,
                        tracked_repo,
                        full_rescan,
                    )
                except Exception:
                    logger.exception(
                        "design_system_auto_extract_failed",
                        scan_id=scan_id,
                        repo=repo_name,
                    )
                _mark(f"E1b_design_system/{repo_name}", phase_t0)

                # Track HEAD SHA per repo
                head_sha = await get_head_sha(repo_path)
                if head_sha:
                    new_shas[repo_path] = head_sha

            # --- Phase B2: Parallel feature synthesis via Claude Code ---
            if _pending_synthesis:
                import asyncio as _aio

                phase_t0 = time.monotonic()
                scan_status.status = "synthesizing_features"
                scan_status.progress_pct = 50

                # Commit so MCP callbacks don't block on our locks
                await db.commit()

                async def _synthesize_repo(task: dict) -> dict:
                    """Run synthesis for one repo. Returns result dict."""
                    from app.config import settings as app_settings
                    from app.mcp.auth import create_internal_mcp_token
                    from app.mcp.server import (
                        clear_synthesis_queue,
                        get_queue_remaining,
                    )

                    rname = task["repo_name"]
                    t0 = time.monotonic()
                    prompt = build_synthesis_prompt(
                        rname,
                        task["overview"],
                        is_workspace,
                    )
                    token = create_internal_mcp_token(org_id)
                    synth_config = ClaudeRunnerConfig(
                        max_turns=scan_cfg.get("max_turns", 40),
                        timeout_seconds=scan_cfg.get("timeout_seconds", 300),
                        output_format="json",
                        mcp=MCPServerConfig(
                            backend_url=app_settings.mcp_backend_url,
                            mcp_token=token,
                        ),
                    )
                    result = await run_claude_code(
                        prompt=prompt,
                        working_dir=task["repo_path"],
                        config=synth_config,
                    )

                    remaining = get_queue_remaining(
                        str(org_id),
                        queue_key=task["queue_key"],
                    )
                    clear_synthesis_queue(
                        str(org_id),
                        queue_key=task["queue_key"],
                    )
                    elapsed = round(time.monotonic() - t0, 1)
                    return {
                        "repo_name": rname,
                        "result": result,
                        "remaining": remaining,
                        "elapsed_s": elapsed,
                    }

                # Run all repos in parallel
                synthesis_outcomes = await _aio.gather(
                    *[_synthesize_repo(t) for t in _pending_synthesis],
                    return_exceptions=True,
                )

                for outcome in synthesis_outcomes:
                    if isinstance(outcome, Exception):
                        logger.exception(
                            "feature_synthesis_exception",
                            error=str(outcome),
                        )
                        continue
                    rname = outcome["repo_name"]
                    result = outcome["result"]
                    remaining = outcome["remaining"]
                    if result.success:
                        logger.info(
                            "feature_synthesis_complete",
                            repo=rname,
                            cost=result.cost_usd,
                            elapsed_s=outcome["elapsed_s"],
                            remaining_clusters=len(remaining),
                        )
                    else:
                        logger.warning(
                            "feature_synthesis_failed",
                            repo=rname,
                            error=result.error,
                            elapsed_s=outcome["elapsed_s"],
                            remaining_clusters=len(remaining),
                        )
                        scan_status.features_skipped += len(remaining)
                        is_timeout = "Timed out" in (result.error or "")
                        if is_timeout:
                            scan_status.synthesis_warning = (
                                f"{rname}: {len(remaining)} feature(s) skipped "
                                "— timed out. Increase timeout in Settings."
                            )
                        else:
                            scan_status.synthesis_warning = (
                                f"{rname}: {len(remaining)} feature(s) skipped — synthesis failed."
                            )

                _mark("B2_synthesis_parallel", phase_t0)

                # Count features actually written to DB
                total_features_synthesized = await ki_repo.count_active(
                    category="feature_registry"
                )

                # --- Phase E2: Re-run skill analysis with feature-based modules ---
                # On full scans, Phase E ran before features existed. Now that
                # features are synthesized, reload the feature map and rebuild
                # skill profiles so modules are feature names, not directories.
                phase_t0 = time.monotonic()
                feature_map_e2 = await _load_feature_map(db, org_id)
                if feature_map_e2:
                    scan_status.status = "analyzing_skills"
                    # Delete old directory-based profiles
                    sp_repo_e2 = SkillProfileRepository(db, org_id=org_id)
                    deleted_profiles = await sp_repo_e2.delete_all_for_org()
                    if deleted_profiles:
                        logger.info("e2_deleted_old_profiles", count=deleted_profiles)

                    total_profiles = 0
                    for repo_path_e2 in repo_paths:
                        entries_e2 = await analyze_repo_skills(
                            repo_path_e2, feature_map=feature_map_e2
                        )
                        for entry in entries_e2:
                            user = email_to_user.get(entry.email.lower())
                            if user is None:
                                continue
                            total_profiles += 1
                            profile = await sp_repo_e2.get_by_user_and_module(
                                user.id, entry.module
                            )
                            if profile:
                                profile.touch_count = entry.touch_count
                                profile.skill_score = entry.skill_score
                                profile.languages = entry.languages
                                profile.last_touch = entry.last_touch
                                profile.feature_id = entry.feature_id
                            else:
                                profile = SkillProfile(
                                    user_id=user.id,
                                    org_id=org_id,
                                    module=entry.module,
                                    feature_id=entry.feature_id,
                                    repo=repo_path_e2,
                                    languages=entry.languages,
                                    skill_score=entry.skill_score,
                                    touch_count=entry.touch_count,
                                    last_touch=entry.last_touch,
                                )
                                db.add(profile)
                        await db.flush()

                _mark("E2_skill_remap", phase_t0)

            # --- Phase B3a: Programmatic same-name merge (workspace only) ---
            phase_t0 = time.monotonic()
            if is_workspace and total_features_synthesized > 0:
                scan_status.status = "merging_features"
                scan_status.progress_pct = 85
                name_merged = await merge_same_name_features(db, org_id)
                if name_merged:
                    logger.info("same_name_merge_done", deactivated=name_merged)

            _mark("B3a_name_merge", phase_t0)

            # --- Phase F: Embed missing items (once, across all repos) ---
            phase_t0 = time.monotonic()
            scan_status.status = "embedding"
            scan_status.progress_pct = 88
            await _embed_missing_items(db, org_id)
            _mark("F_embedding", phase_t0)

            # --- Phase B3a2: Deactivate superseded repo-specific features ---
            phase_t0 = time.monotonic()
            if is_workspace and total_features_synthesized > 0:
                superseded = await deactivate_superseded_repo_features(db, org_id)
                if superseded:
                    logger.info("superseded_cleanup_done", deactivated=superseded)
            _mark("B3a2_superseded", phase_t0)

            # --- Phase B3b: Semantic dedup (any scan with 2+ features) ---
            phase_t0 = time.monotonic()
            if total_features_synthesized >= 2 and is_claude_cli_available():
                dup_groups = await find_semantic_duplicates(db, org_id)
                if dup_groups:
                    scan_status.status = "merging_features"
                    scan_status.progress_pct = 92
                    merge_prompt = build_targeted_merge_prompt(dup_groups)

                    # Commit before launching Claude CLI so the MCP callbacks
                    # don't block on our transaction's row locks / connection.
                    await db.commit()

                    from app.config import settings
                    from app.mcp.auth import create_internal_mcp_token

                    merge_token = create_internal_mcp_token(org_id)
                    merge_config = ClaudeRunnerConfig(
                        max_turns=min(len(dup_groups) * 3, scan_cfg.get("max_turns", 40)),
                        timeout_seconds=scan_cfg.get("timeout_seconds", 300),
                        output_format="json",
                        mcp=MCPServerConfig(
                            backend_url=settings.mcp_backend_url,
                            mcp_token=merge_token,
                        ),
                    )
                    merge_result = await run_claude_code(
                        prompt=merge_prompt,
                        working_dir=str(Path(repo_paths[0]).parent),
                        config=merge_config,
                    )

                    if merge_result.success:
                        logger.info(
                            "semantic_merge_complete",
                            groups=len(dup_groups),
                            cost=merge_result.cost_usd,
                        )
                        # Re-embed items created by the merge
                        await _embed_missing_items(db, org_id)
                    else:
                        logger.warning(
                            "semantic_merge_failed",
                            error=merge_result.error,
                        )

                    # Re-load org after commit (session state was cleared)
                    org = await org_repo.get_by_id(org_id)
                    config = dict(org.config or {})

            _mark("B3b_semantic_merge", phase_t0)

            # Deduplicate items created by concurrent MCP retries
            phase_t0 = time.monotonic()
            deduped = await dedup_merged_features(db, org_id)
            if deduped:
                logger.info("post_merge_dedup", deactivated=deduped)

            _mark("dedup", phase_t0)

            # Hard-delete deactivated feature_registry items (merge artifacts).
            # These were repo-specific features replaced by merged versions —
            # keeping them clutters the DB with NULL-embedding inactive rows.
            phase_t0 = time.monotonic()
            cleanup_deleted = await ki_repo.delete_inactive_by_category("feature_registry")
            if cleanup_deleted:
                await db.flush()
                logger.info(
                    "merge_artifact_cleanup",
                    scan_id=scan_id,
                    deleted=cleanup_deleted,
                )
            _mark("cleanup", phase_t0)

            # Authoritative feature count from DB (not GitNexus cluster count)
            actual_features = await ki_repo.count_active(category="feature_registry")

            # --- Phase G: Save last commit SHAs + scan results ---
            # Update tracked_repositories with new SHAs and counts (via repo_id FK)
            for rp, sha in new_shas.items():
                tracked = await tracked_repo_repo.get_by_path(rp)
                if tracked:
                    k_count = await ki_repo.count_by_repo_id(tracked.id)
                    f_count = await ki_repo.count_by_repo_id(
                        tracked.id, category="feature_registry"
                    )
                    await tracked_repo_repo.update_after_scan(rp, sha, k_count, f_count)

            # Legacy config compat
            config.setdefault("knowledge", {})
            config["knowledge"]["repo_shas"] = new_shas
            if len(repo_paths) == 1 and new_shas:
                config["knowledge"]["last_commit_sha"] = next(iter(new_shas.values()))
            # Persist last scan results for the stats endpoint
            from datetime import UTC, datetime

            config["knowledge"]["last_scan"] = {
                "completed_at": datetime.now(UTC).isoformat(),
                "repos_scanned": len(repo_paths),
                "features_indexed": actual_features,
                "profiles_found": total_profiles,
                "unmatched_authors": len(all_unmatched),
                "scan_mode": overall_mode,
            }
            org.config = config
            await db.flush()
            await db.commit()

            scan_status.features_indexed = actual_features
            scan_status.profiles_found = total_profiles
            scan_status.stale_cleaned = total_stale
            scan_status.unmatched_authors = all_unmatched[:20]
            scan_status.scan_mode = overall_mode
            scan_status.status = "completed"
            scan_status.progress_pct = 100

            total_elapsed = round(time.monotonic() - pipeline_t0, 1)
            logger.info(
                "scan_complete",
                scan_id=scan_id,
                repos=len(repo_paths),
                mode=overall_mode,
                features=actual_features,
                profiles=total_profiles,
                unmatched=len(all_unmatched),
                total_seconds=total_elapsed,
                phase_timings=phase_timings,
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
        if user_id:
            from app.services.notification_service import send_scan_notification

            send_scan_notification(
                scan_id=scan_id,
                user_id=user_id,
                org_id=str(org_id),
                completed=False,
                error_message=str(exc)[:500],
            )
