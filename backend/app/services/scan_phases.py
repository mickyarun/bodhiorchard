"""Individual scan pipeline phase functions.

Each function implements one phase of the scan pipeline with explicit
parameters (no closure variables).  Extracted from ``run_scan_pipeline()``
to keep the orchestrator readable.
"""

import time
import uuid
from pathlib import Path

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.user import OrgToUser, User, UserRole
from app.repositories.knowledge_item import KnowledgeItemRepository
from app.repositories.user import UserRepository
from app.schemas.skills import ScanStatus
from app.services.claude_runner import (
    ClaudeRunnerConfig,
    MCPServerConfig,
    is_claude_cli_available,
    run_claude_code,
)
from app.services.feature_merger import dedup_merged_features
from app.services.git_analyzer import analyze_repo_skills, get_diff_since
from app.services.scan_helpers import (
    embed_missing_items,
    load_feature_map,
    upsert_skill_profiles,
)

logger = structlog.get_logger(__name__)


async def phase_a_scan_mode(
    db: AsyncSession,
    org_id: uuid.UUID,
    repo_path: str,
    repo_name: str,
    full_rescan: bool,
    last_sha: str | None,
    ki_repo: KnowledgeItemRepository,
    scan_id: str,
) -> tuple[bool, bool, list[str]]:
    """Phase A: Determine scan mode (incremental vs full).

    Args:
        db: Async database session.
        org_id: Organization UUID.
        repo_path: Absolute path to the repository.
        repo_name: Name of the repository.
        full_rescan: Whether the user forced a full rescan.
        last_sha: Last known commit SHA, or None.
        ki_repo: Knowledge item repository instance.
        scan_id: Scan identifier for logging.

    Returns:
        Tuple of (is_incremental, full_rescan, deleted_files).
        ``full_rescan`` may be updated to True if no scan features exist.
    """
    from app.services.scan_pipeline import INCREMENTAL_THRESHOLD

    is_incremental = False
    deleted_files: list[str] = []

    # Check if we have any scan-sourced features — if not, force
    # full scan even if last_sha exists
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

        change_ratio = total_changed / diff.total_repo_files if diff.total_repo_files > 0 else 1.0

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

    return is_incremental, full_rescan, deleted_files


async def phase_b1_repo_setup(
    db: AsyncSession,
    org_id: uuid.UUID,
    repo_path: str,
    repo_name: str,
    tracked_repo: object | None,
    scan_id: str,
    scan_status: ScanStatus,
) -> None:
    """Phase B1: Worktrees, MCP init, hooks, .gitignore, commit+push+PR.

    Args:
        db: Async database session.
        org_id: Organization UUID.
        repo_path: Absolute path to the repository.
        repo_name: Name of the repository.
        tracked_repo: TrackedRepository model instance (or None).
        scan_id: Scan identifier for logging.
        scan_status: ScanStatus instance to update with PR message.
    """
    from app.config import settings as app_settings
    from app.mcp.auth import create_internal_mcp_token
    from app.services.git_operations import _detect_develop_branch, _detect_main_branch
    from app.services.repo_setup import (
        add_bodhigrove_gitignore,
        add_prepare_script,
        commit_and_push_bodhigrove_setup,
        create_setup_pr,
        ensure_repo_worktrees,
        init_bodhigrove_mcp_in_repo,
        install_hooks,
    )

    try:
        main_wt, develop_wt = await ensure_repo_worktrees(repo_path)

        # Persist detected branches to tracked_repositories
        if tracked_repo:
            if tracked_repo.main_branch is None:  # type: ignore[union-attr]
                detected_main = await _detect_main_branch(repo_path)
                if detected_main:
                    tracked_repo.main_branch = detected_main  # type: ignore[union-attr]
            if tracked_repo.develop_branch is None:  # type: ignore[union-attr]
                detected_dev = await _detect_develop_branch(repo_path)
                if detected_dev:
                    tracked_repo.develop_branch = detected_dev  # type: ignore[union-attr]

        # Init Bodhigrove MCP in repo (skips if already configured)
        mcp_token = create_internal_mcp_token(org_id)
        mcp_changed = await init_bodhigrove_mcp_in_repo(
            repo_path, app_settings.public_url, mcp_token
        )

        # Install git hooks to .githooks/ + set core.hooksPath
        hooks_changed = await install_hooks(repo_path, app_settings.public_url, str(org_id))

        # Add .bodhigrove/ to .gitignore
        gitignore_changed = add_bodhigrove_gitignore(repo_path)

        # Add prepare script to package.json
        prepare_changed = add_prepare_script(repo_path)

        # Branch, commit, push setup files, and create PR
        any_changed = mcp_changed or hooks_changed or gitignore_changed or prepare_changed
        if any_changed:
            base = (
                tracked_repo.main_branch  # type: ignore[union-attr]
                if tracked_repo and tracked_repo.main_branch  # type: ignore[union-attr]
                else "main"
            )
            pushed_branch = await commit_and_push_bodhigrove_setup(repo_path, base)
            if pushed_branch:
                logger.info(
                    "bodhigrove_setup_branch_pushed",
                    repo=repo_name,
                    branch=pushed_branch,
                )
                pr_url = await create_setup_pr(repo_path, base, pushed_branch)
                if pr_url:
                    logger.info(
                        "bodhigrove_setup_pr_created",
                        repo=repo_name,
                        url=pr_url,
                    )
                else:
                    scan_status.setup_pr_message = (
                        f"Setup branch '{pushed_branch}' pushed "
                        f"to {repo_name}. Create a PR manually "
                        "to merge the Bodhigrove config files."
                    )

            await db.flush()
    except Exception:
        logger.exception(
            "scan_repo_setup_failed",
            scan_id=scan_id,
            repo=repo_name,
        )


async def phase_e_skills(
    db: AsyncSession,
    org_id: uuid.UUID,
    repo_path: str,
    skill_entries: list,
    email_to_user: dict[str, User],
    scan_cfg: dict,
) -> tuple[int, list[str], dict[str, User]]:
    """Phase E: Git skill analysis — auto-create members and upsert profiles.

    Args:
        db: Async database session.
        org_id: Organization UUID.
        repo_path: Absolute path to the repository.
        skill_entries: Skill entries from ``analyze_repo_skills()``.
        email_to_user: Current email → User mapping.
        scan_cfg: Scan configuration dict from org config.

    Returns:
        Tuple of (profiles_count, unmatched_emails, updated_email_to_user).
    """
    user_repo = UserRepository(db)

    # Auto-create members from git authors if enabled
    auto_create = scan_cfg.get("auto_create_members", True)
    if auto_create and skill_entries:
        email_to_user = await user_repo.get_email_map(org_id)
        seen_emails: set[str] = set()
        for entry in skill_entries:
            email_lower = entry.email.lower()
            if email_lower in email_to_user or email_lower in seen_emails:
                continue
            seen_emails.add(email_lower)
            new_user = User(
                email=entry.email,
                name=entry.author_name,
                password_hash=hash_password("changeme123"),
                is_active=True,
            )
            db.add(new_user)
            await db.flush()
            # Create org membership for the auto-created user
            membership = OrgToUser(user_id=new_user.id, org_id=org_id, role=UserRole.DEVELOPER)
            db.add(membership)
        await db.flush()
        email_to_user = await user_repo.get_email_map(org_id)

    count, unmatched = await upsert_skill_profiles(db, org_id, skill_entries, email_to_user)
    return count, unmatched, email_to_user


async def phase_b2_synthesis(
    db: AsyncSession,
    org_id: uuid.UUID,
    pending_synthesis: list[dict],
    is_workspace: bool,
    scan_cfg: dict,
    scan_status: ScanStatus,
    ki_repo: KnowledgeItemRepository,
) -> int:
    """Phase B2: Parallel feature synthesis via Claude Code.

    Args:
        db: Async database session.
        org_id: Organization UUID.
        pending_synthesis: List of synthesis task dicts.
        is_workspace: Whether this is a multi-repo workspace scan.
        scan_cfg: Scan configuration dict from org config.
        scan_status: ScanStatus instance to update.
        ki_repo: Knowledge item repository instance.

    Returns:
        Total features synthesized (from DB count).
    """
    if not pending_synthesis:
        return 0

    import asyncio as _aio

    from app.services.scan_pipeline import build_synthesis_prompt

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
        *[_synthesize_repo(t) for t in pending_synthesis],
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

    # Count features actually written to DB
    return await ki_repo.count_active(category="feature_registry")


async def phase_e2_skill_remap(
    db: AsyncSession,
    org_id: uuid.UUID,
    repo_paths: list[str],
    email_to_user: dict[str, User],
    scan_status: ScanStatus,
) -> int:
    """Phase E2: Re-run skill analysis with feature-based modules.

    On full scans, Phase E ran before features existed. Now that
    features are synthesized, reload the feature map and rebuild
    skill profiles so modules are feature names, not directories.

    Only wipes old profiles if the new feature-based analysis covers
    at least 70% of the old profile count, to avoid data loss when
    the feature map is sparse (Bug 6 fix).

    Args:
        db: Async database session.
        org_id: Organization UUID.
        repo_paths: List of all repo paths being scanned.
        email_to_user: Mapping of lowercase email → User.
        scan_status: ScanStatus instance to update.

    Returns:
        Total profiles upserted.
    """
    from app.repositories.skill_profile import SkillProfileRepository

    feature_map_e2 = await load_feature_map(db, org_id)
    if not feature_map_e2:
        return 0

    scan_status.status = "analyzing_skills"
    sp_repo_e2 = SkillProfileRepository(db, org_id=org_id)

    # Run new analysis first (before deleting anything)
    new_entries = []
    for repo_path_e2 in repo_paths:
        entries_e2 = await analyze_repo_skills(repo_path_e2, feature_map=feature_map_e2)
        new_entries.extend(entries_e2)

    existing_count = await sp_repo_e2.count_profiles()

    # Only wipe+replace if new analysis has good coverage
    if not existing_count or len(new_entries) >= existing_count * 0.7:
        deleted_profiles = await sp_repo_e2.delete_all_for_org()
        if deleted_profiles:
            logger.info("e2_deleted_old_profiles", count=deleted_profiles)
        total_profiles = 0
        count, _ = await upsert_skill_profiles(db, org_id, new_entries, email_to_user)
        total_profiles = count
    else:
        # Sparse feature map — update feature_ids on matching profiles
        # without wiping unmatched ones.
        logger.warning(
            "e2_sparse_map_partial_update",
            new_entries=len(new_entries),
            existing=existing_count,
        )
        count, _ = await upsert_skill_profiles(db, org_id, new_entries, email_to_user)
        total_profiles = existing_count

    return total_profiles


async def phase_b3_merge(
    db: AsyncSession,
    org_id: uuid.UUID,
    repo_paths: list[str],
    is_workspace: bool,
    total_features_synthesized: int,
    scan_cfg: dict,
    scan_status: ScanStatus,
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
        scan_status: ScanStatus instance to update.
        ki_repo: Knowledge item repository instance.

    Returns:
        Dict with possibly updated ``config`` (after commit/reload).
    """
    from app.repositories.organization import OrganizationRepository
    from app.services.scan_pipeline import MERGE_BATCH_SIZE, build_merge_prompt

    # --- Embed missing items ---
    scan_status.status = "embedding"
    scan_status.progress_pct = 88
    await embed_missing_items(db, org_id)

    # --- LLM-based cross-repo merge (multi-repo scans with 2+ features) ---
    config: dict = {}
    if is_workspace and total_features_synthesized >= 2 and is_claude_cli_available():
        scan_status.status = "merging_features"
        scan_status.progress_pct = 92

        # Collect features with their repo names for the merge prompt
        from app.models.tracked_repository import TrackedRepository

        features = await ki_repo.list_active(category="feature_registry", limit=1000)

        feature_dicts: list[dict] = []
        for f in features:
            repo_ids = await ki_repo.get_repo_ids(f.id)
            rnames: list[str] = []
            for rid in repo_ids:
                tracked = await db.get(TrackedRepository, rid)
                if tracked:
                    rnames.append(tracked.name)
            feature_dicts.append({
                "title": f.title,
                "repo_names": rnames,
                "tags": f.tags or [],
            })

        if feature_dicts:
            await db.commit()

            from app.config import settings
            from app.mcp.auth import create_internal_mcp_token

            # Process in batches, re-run until no more merges
            prev_count = len(feature_dicts)
            for _pass in range(3):  # Max 3 passes to prevent infinite loops
                for batch_start in range(0, len(feature_dicts), MERGE_BATCH_SIZE):
                    batch = feature_dicts[batch_start:batch_start + MERGE_BATCH_SIZE]
                    merge_prompt = build_merge_prompt(batch)

                    merge_token = create_internal_mcp_token(org_id)
                    merge_cfg = ClaudeRunnerConfig(
                        max_turns=scan_cfg.get("max_turns", 40),
                        timeout_seconds=scan_cfg.get("timeout_seconds", 300),
                        output_format="json",
                        mcp=MCPServerConfig(
                            backend_url=settings.mcp_backend_url,
                            mcp_token=merge_token,
                        ),
                    )
                    result = await run_claude_code(
                        prompt=merge_prompt,
                        working_dir=str(Path(repo_paths[0]).parent),
                        config=merge_cfg,
                    )
                    if result.success:
                        logger.info(
                            "llm_merge_pass_complete",
                            pass_num=_pass + 1,
                            batch_size=len(batch),
                            cost=result.cost_usd,
                        )
                    else:
                        logger.warning("llm_merge_failed", error=result.error)

                # Check if merges happened
                new_count = await ki_repo.count_active(category="feature_registry")
                if new_count >= prev_count:
                    break  # No merges this pass
                prev_count = new_count

            # Re-embed after merge
            await embed_missing_items(db, org_id)

            # Re-load org after commit
            org_repo = OrganizationRepository(db)
            org = await org_repo.get_by_id(org_id)
            config = dict(org.config or {})

    # Deduplicate items created by concurrent MCP retries
    deduped = await dedup_merged_features(db, org_id)
    if deduped:
        logger.info("post_merge_dedup", deactivated=deduped)

    # Hard-delete deactivated feature_registry items
    cleanup_deleted = await ki_repo.delete_inactive_by_category("feature_registry")
    if cleanup_deleted:
        await db.flush()
        logger.info("merge_artifact_cleanup", deleted=cleanup_deleted)

    # Auto-link orphan features
    from app.services.scan_helpers import link_orphan_features

    await link_orphan_features(db, org_id, ki_repo)

    return config


async def phase_g_persist(
    db: AsyncSession,
    org_id: uuid.UUID,
    repo_paths: list[str],
    new_shas: dict[str, str],
    config: dict,
    total_profiles: int,
    all_unmatched: list[str],
    overall_mode: str,
    ki_repo: KnowledgeItemRepository,
) -> int:
    """Phase G: Save last commit SHAs + scan results to org config.

    Args:
        db: Async database session.
        org_id: Organization UUID.
        repo_paths: List of all repo paths scanned.
        new_shas: Mapping of repo_path → HEAD SHA.
        config: Organization config dict to update.
        total_profiles: Total skill profiles found.
        all_unmatched: List of unmatched author emails.
        overall_mode: Scan mode ('full' or 'incremental').
        ki_repo: Knowledge item repository instance.

    Returns:
        Authoritative feature count from DB.
    """
    from app.repositories.organization import OrganizationRepository
    from app.repositories.tracked_repository import TrackedRepoRepository

    tracked_repo_repo = TrackedRepoRepository(db, org_id=org_id)

    # Update tracked_repositories with new SHAs and counts
    for rp, sha in new_shas.items():
        tracked = await tracked_repo_repo.get_by_path(rp)
        if tracked:
            k_count = await ki_repo.count_by_repo_id(tracked.id)
            f_count = await ki_repo.count_by_repo_id(tracked.id, category="feature_registry")
            await tracked_repo_repo.update_after_scan(rp, sha, k_count, f_count)

    # Authoritative feature count from DB
    actual_features = await ki_repo.count_active(category="feature_registry")

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

    org_repo = OrganizationRepository(db)
    org = await org_repo.get_by_id(org_id)
    org.config = config
    await db.flush()
    await db.commit()

    return actual_features
