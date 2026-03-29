"""Tree data aggregation service for the Living Tree Dashboard.

Collects data from git history, BUDs, bugs, agent logs,
and member profiles to build the TreeData response.

Architecture:
  - Trunk = organization
  - Limbs = tracked repositories (RepoLimbData)
  - Branches = top-level directories within each repo
  - Leaves = recently committed files (evergreen color model)
"""

import asyncio
import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import TypedDict

import structlog
from cachetools import TTLCache
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_activity import AgentActivityLog
from app.models.agent_log import AgentLog
from app.models.bud import BUDDocument
from app.models.bud_agent_task import BUDAgentTask
from app.models.bug import Bug, BugStatus
from app.models.knowledge_item import KnowledgeItem, KnowledgeRepoLink
from app.models.skill_profile import SkillProfile
from app.models.tracked_repository import TrackedRepository
from app.models.user import User
from app.schemas.dashboard import (
    AgentActivityItem,
    BranchData,
    BUDItem,
    BUDStageCount,
    FeatureItem,
    FeatureSkillSummary,
    LeafData,
    MemberActivity,
    RelationshipArc,
    RepoLimbData,
    SecurityThreat,
    TreeData,
)
from app.services.presence_cache import get_presence_state

logger = structlog.get_logger(__name__)

# TTL cache: one entry per org, 5-minute expiry
_cache: TTLCache[str, TreeData] = TTLCache(maxsize=64, ttl=300)

# Hardcoded branch count for single-repo visual balance
_SINGLE_REPO_BRANCH_COUNT = 8


async def get_tree_data(
    db: AsyncSession,
    org_id: uuid.UUID,
    tracked_repos: list[tuple[str, str]],
    *,
    refresh: bool = False,
) -> TreeData:
    """Build the complete TreeData for the Living Tree dashboard.

    Args:
        db: Async database session.
        org_id: Organization UUID.
        tracked_repos: List of (path, name) tuples for tracked repositories.
        refresh: If True, bypass the cache.

    Returns:
        Aggregated TreeData for the frontend.
    """
    cache_key = str(org_id)
    if not refresh and cache_key in _cache:
        return _cache[cache_key]

    tree = TreeData(org_id=str(org_id))

    # 1. Collect repo structure — builds tree.repos[] with branches from directories
    file_branch_map = await _collect_repo_structure(tree, tracked_repos)

    # 2. Collect bugs BEFORE git history so we can cross-reference
    bugged_modules = await _collect_bugs(db, org_id, tree)

    # 3. Collect git history with evergreen colors + bug cross-ref
    await _collect_git_history(tree, tracked_repos, file_branch_map, bugged_modules)

    # 4. Classify each repo's growth stage
    for repo_limb in tree.repos:
        repo_limb.growth_stage = _classify_repo_growth_stage(repo_limb)

    # 5. DB queries (AsyncSession is not concurrency-safe)
    # Features first: builds the bud→branch map needed by _collect_bud_stages
    await _collect_features(db, org_id, tree, file_branch_map)
    await _collect_bud_stages(db, org_id, tree)
    await _collect_agents(db, org_id, tree)
    await _collect_members(db, org_id, tree)

    # 6. Populate tree.branches as union of all repo branches (backward compat)
    tree.branches = []
    for repo_limb in tree.repos:
        tree.branches.extend(repo_limb.branches)

    # 7. Detect cross-repo relationships from shared branch/community names
    _collect_cross_repo_relationships(tree)

    # 8. Compute feature skill summaries (bus factor)
    await _compute_feature_skills(db, org_id, tree)

    _cache[cache_key] = tree
    return tree


async def _collect_repo_structure(
    tree: TreeData,
    tracked_repos: list[tuple[str, str]],
) -> dict[str, str]:
    """Build per-repo RepoLimbData from directory structure.

    Returns a file->branch_name mapping for use by _collect_git_history.
    """
    file_branch_map: dict[str, str] = {}
    is_single_repo = len(tracked_repos) == 1

    for repo_path, repo_name in tracked_repos:
        repo_limb = RepoLimbData(repo_name=repo_name, repo_path=repo_path)

        if is_single_repo:
            # Single-repo: hardcoded 6-8 branches for visual balance
            await _load_hardcoded_branches(repo_limb, repo_path, file_branch_map)
        else:
            await _load_branches_from_directories(repo_limb, repo_path, file_branch_map)

        tree.repos.append(repo_limb)

    return file_branch_map


async def _load_hardcoded_branches(
    repo_limb: RepoLimbData,
    repo_path: str,
    file_branch_map: dict[str, str],
) -> None:
    """Create hardcoded 6-8 branches from top-level dirs for a single-repo tree."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "git",
            "ls-files",
            cwd=repo_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await proc.communicate()
        files = stdout.decode().strip().splitlines()

        dir_counts: dict[str, int] = {}
        for f in files:
            parts = f.split("/", 1)
            if len(parts) >= 2:
                top_dir = parts[0]
                if top_dir.startswith("."):
                    continue
                dir_counts[top_dir] = dir_counts.get(top_dir, 0) + 1
                file_branch_map[f] = top_dir
            else:
                file_branch_map[f] = "root"
                dir_counts["root"] = dir_counts.get("root", 0) + 1

        sorted_dirs = sorted(dir_counts.items(), key=lambda x: x[1], reverse=True)
        target = min(_SINGLE_REPO_BRANCH_COUNT, max(len(sorted_dirs), 6))

        if len(sorted_dirs) > target:
            main_dirs = sorted_dirs[: target - 1]
            other_count = sum(c for _, c in sorted_dirs[target - 1 :])
            main_dirs.append(("other", other_count))
            merged_names = {name for name, _ in sorted_dirs[target - 1 :]}
            for f, branch in list(file_branch_map.items()):
                if branch in merged_names:
                    file_branch_map[f] = "other"
            sorted_dirs = main_dirs
        elif len(sorted_dirs) < 6:
            generic_names = ["core", "utils", "config", "docs", "tests", "scripts"]
            for name in generic_names:
                if len(sorted_dirs) >= 6:
                    break
                if name not in dict(sorted_dirs):
                    sorted_dirs.append((name, 0))

        for dir_name, count in sorted_dirs:
            repo_limb.branches.append(
                BranchData(
                    name=dir_name,
                    file_count=count,
                    commit_count=0,
                    health="healthy",
                )
            )

        repo_limb.total_files = len(files)
        logger.info(
            "hardcoded_branches_loaded",
            count=len(repo_limb.branches),
            repo=repo_path,
        )

    except Exception:
        logger.warning("hardcoded_branches_failed", path=repo_path)


async def _load_branches_from_directories(
    repo_limb: RepoLimbData,
    repo_path: str,
    file_branch_map: dict[str, str],
) -> None:
    """Create branches from top-level directory structure as fallback."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "git",
            "ls-files",
            cwd=repo_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await proc.communicate()
        files = stdout.decode().strip().splitlines()

        dir_counts: dict[str, int] = {}
        for f in files:
            parts = f.split("/", 1)
            if len(parts) >= 2:
                top_dir = parts[0]
                if top_dir.startswith("."):
                    continue
                dir_counts[top_dir] = dir_counts.get(top_dir, 0) + 1
                file_branch_map[f] = top_dir
            else:
                file_branch_map[f] = "root"
                dir_counts["root"] = dir_counts.get("root", 0) + 1

        sorted_dirs = sorted(dir_counts.items(), key=lambda x: x[1], reverse=True)

        if len(sorted_dirs) > 20:
            main_dirs = sorted_dirs[:19]
            other_count = sum(c for _, c in sorted_dirs[19:])
            main_dirs.append(("other", other_count))
            merged_names = {name for name, _ in sorted_dirs[19:]}
            for f, branch in list(file_branch_map.items()):
                if branch in merged_names:
                    file_branch_map[f] = "other"
            sorted_dirs = main_dirs

        for dir_name, count in sorted_dirs:
            repo_limb.branches.append(
                BranchData(
                    name=dir_name,
                    file_count=count,
                    commit_count=0,
                    health="healthy",
                )
            )

        repo_limb.total_files = len(files)
        logger.info(
            "directory_branches_loaded",
            count=len(sorted_dirs),
            repo=repo_path,
        )

    except Exception:
        logger.warning("directory_branches_failed", path=repo_path)


async def _collect_git_history(
    tree: TreeData,
    tracked_repos: list[tuple[str, str]],
    file_branch_map: dict[str, str],
    bugged_modules: set[str],
) -> None:
    """Collect commit data from git log for leaves and project age.

    Uses the evergreen color model:
    - bugged files -> wilted (brown)
    - <=7 days -> freshGreen (bright)
    - <=30 days -> mediumGreen
    - >30 days -> deepGreen (stable, healthy)
    """
    now = datetime.now(UTC)

    for repo_path, _repo_name in tracked_repos:
        repo_limb = next((r for r in tree.repos if r.repo_path == repo_path), None)
        if not repo_limb:
            continue

        repo_branches = repo_limb.branches

        try:
            # Get total file count
            proc = await asyncio.create_subprocess_exec(
                "git",
                "ls-files",
                cwd=repo_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await proc.communicate()
            files = stdout.decode().strip().splitlines()
            file_count = len(files)
            tree.total_files += file_count
            repo_limb.total_files = file_count

            # Get first commit date for project age
            proc = await asyncio.create_subprocess_exec(
                "git",
                "log",
                "--reverse",
                "--format=%aI",
                "-1",
                cwd=repo_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await proc.communicate()
            first_date_str = stdout.decode().strip()
            if first_date_str:
                first_date = datetime.fromisoformat(first_date_str)
                age = (now - first_date).days
                tree.project_age_days = max(tree.project_age_days, age)

            # Get recent commits (last 90 days) for leaves
            since_date = (now - timedelta(days=90)).strftime("%Y-%m-%d")
            proc = await asyncio.create_subprocess_exec(
                "git",
                "log",
                f"--since={since_date}",
                "--format=%H %aI",
                "--name-only",
                cwd=repo_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await proc.communicate()
            lines = stdout.decode().strip().splitlines()

            current_date: datetime | None = None
            leaf_count = 0
            max_leaves = 200
            total_commits = 0

            for line in lines:
                if not line.strip():
                    continue
                parts = line.split(" ", 2)
                if len(parts) >= 2 and len(parts[0]) == 40:
                    try:
                        current_date = datetime.fromisoformat(parts[1])
                        total_commits += 1
                    except ValueError:
                        current_date = None
                elif current_date and leaf_count < max_leaves:
                    file_path = line.strip()
                    age_days = (now - current_date).days

                    # Evergreen color model
                    is_bugged = _is_file_bugged(file_path, bugged_modules)
                    if is_bugged:
                        color = "wilted"
                    elif age_days <= 7:
                        color = "freshGreen"
                    elif age_days <= 30:
                        color = "mediumGreen"
                    else:
                        color = "deepGreen"

                    branch_name = _file_to_branch(file_path, repo_branches, file_branch_map)
                    for branch in repo_branches:
                        if branch.name == branch_name:
                            branch.leaves.append(
                                LeafData(
                                    path=file_path,
                                    age_days=age_days,
                                    color=color,
                                    branch_name=branch_name,
                                    has_bug=is_bugged,
                                )
                            )
                            branch.commit_count += 1
                            leaf_count += 1
                            break

            repo_limb.total_commits = total_commits

        except Exception:
            logger.warning("git_history_collect_failed", path=repo_path)

    # Compute branch health (bug-based)
    for repo_limb in tree.repos:
        for branch in repo_limb.branches:
            branch.health = _compute_branch_health(branch)
        repo_limb.health = _compute_repo_health(repo_limb)


def _is_file_bugged(file_path: str, bugged_modules: set[str]) -> bool:
    """Check if a file belongs to a bugged module."""
    file_lower = file_path.lower()
    for module in bugged_modules:
        module_lower = module.lower()
        if file_lower.startswith(module_lower + "/") or file_lower == module_lower:
            return True
        first_component = file_path.split("/")[0].lower()
        if first_component == module_lower:
            return True
    return False


def _file_to_branch(
    file_path: str,
    branches: list[BranchData],
    file_branch_map: dict[str, str],
) -> str:
    """Map a file path to the best-matching branch name."""
    if file_path in file_branch_map:
        return file_branch_map[file_path]

    parts = file_path.split("/")
    if len(parts) >= 2:
        module = parts[0]
        for branch in branches:
            if module.lower() in branch.name.lower():
                return branch.name
    return branches[0].name if branches else "root"


def _compute_branch_health(branch: BranchData) -> str:
    """Classify branch health based on bug presence."""
    bugged_leaves = sum(1 for leaf in branch.leaves if leaf.has_bug)
    branch.bug_count = bugged_leaves
    total = len(branch.leaves)

    if bugged_leaves > 0:
        ratio = bugged_leaves / max(total, 1)
        if ratio >= 0.3:
            return "wilted"
        return "dormant"

    if total == 0:
        return "dormant"

    fresh = sum(1 for leaf in branch.leaves if leaf.color in ("freshGreen", "mediumGreen"))
    if fresh / total >= 0.3:
        return "thriving"
    return "healthy"


def _compute_repo_health(repo_limb: RepoLimbData) -> str:
    """Compute overall repo health from its branches."""
    if not repo_limb.branches:
        return "dormant"

    healths = [b.health for b in repo_limb.branches]
    if "wilted" in healths:
        return "wilted"
    if all(h == "dormant" for h in healths):
        return "dormant"
    if any(h == "thriving" for h in healths):
        return "thriving"
    return "healthy"


def _classify_repo_growth_stage(repo_limb: RepoLimbData) -> str:
    """Classify a repo's visual growth stage based on size and activity."""
    files = repo_limb.total_files
    branches = len(repo_limb.branches)
    commits = repo_limb.total_commits

    if files < 20 and commits < 50:
        return "sprout"
    if files < 100 and branches < 5:
        return "sapling"
    if files < 500:
        return "medium"
    return "mature"


async def _collect_bud_stages(db: AsyncSession, org_id: uuid.UUID, tree: TreeData) -> None:
    """Count BUDs at each lifecycle stage and collect individual BUD items.

    Uses tree.features (already populated) to build a bud_number→branch_name
    map so BUDs inherit the repo assignment of their linked feature.
    """
    result = await db.execute(
        select(BUDDocument.status, func.count())
        .where(BUDDocument.org_id == org_id)
        .group_by(BUDDocument.status)
    )
    counts = BUDStageCount()
    for status_val, count in result.all():
        status_str = status_val.value if hasattr(status_val, "value") else str(status_val)
        if hasattr(counts, status_str):
            setattr(counts, status_str, count)
    tree.bud_stages = counts

    # Build bud_number → (branch_name, repo_name) map from features that reference BUDs
    bud_branch_map: dict[int, str] = {}
    bud_repo_map: dict[int, str] = {}
    for feat in tree.features:
        if feat.from_bud is not None:
            if feat.branch_name:
                bud_branch_map[feat.from_bud] = feat.branch_name
            if feat.repo_name:
                bud_repo_map[feat.from_bud] = feat.repo_name

    # testing and uat render as flowers; prod and closed render as fruit
    result = await db.execute(
        select(BUDDocument.bud_number, BUDDocument.title, BUDDocument.status)
        .where(BUDDocument.org_id == org_id)
        .where(BUDDocument.status.in_(["testing", "uat", "prod", "closed"]))
        .order_by(BUDDocument.bud_number)
        .limit(50)
    )
    for bud_number, title, status_val in result.all():
        status_str = status_val.value if hasattr(status_val, "value") else str(status_val)
        tree.buds.append(
            BUDItem(
                bud_number=bud_number,
                title=title,
                status=status_str,
                branch_name=bud_branch_map.get(bud_number),
                repo_name=bud_repo_map.get(bud_number),
            )
        )


class _FeatureGroup(TypedDict):
    title: str | None
    source_ref: str | None
    feature_status: str | None
    repo_paths: list[str]
    code_locations: dict[str, list[str]]
    per_repo_code_locations: dict[str, dict[str, list[str]]]


async def _collect_features(
    db: AsyncSession,
    org_id: uuid.UUID,
    tree: TreeData,
    file_branch_map: dict[str, str],
) -> None:
    """Collect features from the feature registry with BUD linkage.

    JOINs knowledge_to_repo → tracked_repositories to resolve the repo(s)
    each feature belongs to, then maps repo_path → first branch for placement.

    A feature linked to multiple repos via knowledge_to_repo is emitted once
    per linked repo so it appears under each repo in the graph. Features with
    no repo link are still emitted with repo_name=None.
    """
    result = await db.execute(
        select(
            KnowledgeItem.id.label("ki_id"),
            KnowledgeItem.title,
            KnowledgeItem.source_ref,
            KnowledgeItem.feature_status,
            KnowledgeRepoLink.code_locations,
            TrackedRepository.path.label("repo_path"),
        )
        .outerjoin(
            KnowledgeRepoLink,
            KnowledgeRepoLink.knowledge_id == KnowledgeItem.id,
        )
        .outerjoin(
            TrackedRepository,
            TrackedRepository.id == KnowledgeRepoLink.repo_id,
        )
        .where(KnowledgeItem.org_id == org_id)
        .where(KnowledgeItem.category == "feature_registry")
        .where(KnowledgeItem.is_active.is_(True))
        .order_by(KnowledgeItem.created_at.desc())
    )
    rows = result.all()

    # Group rows by knowledge item ID to deduplicate multi-repo joins.
    # Each feature maps to a list of repo_paths it is linked to.
    # code_locations are merged from all junction links.
    from app.services.scan_helpers import merge_code_locations

    features_by_id: dict[uuid.UUID, _FeatureGroup] = {}
    for ki_id, title, source_ref, feature_status, code_locs, repo_path in rows:
        if ki_id not in features_by_id:
            features_by_id[ki_id] = {
                "title": title,
                "source_ref": source_ref,
                "feature_status": feature_status,
                "repo_paths": [],
                "code_locations": code_locs or {},
                "per_repo_code_locations": {},
            }
        else:
            # Merge code_locations from additional junction rows
            features_by_id[ki_id]["code_locations"] = merge_code_locations(
                features_by_id[ki_id]["code_locations"], code_locs
            )
        if repo_path:
            features_by_id[ki_id]["repo_paths"].append(repo_path)
        if repo_path and code_locs:
            features_by_id[ki_id]["per_repo_code_locations"][repo_path] = code_locs

    tree.total_features = len(features_by_id)

    # Build a quick lookup: repo_path → (repo_name, first_branch)
    repo_lookup: dict[str, tuple[str, str | None]] = {}
    for repo in tree.repos:
        first_branch = repo.branches[0].name if repo.branches else None
        repo_lookup[repo.repo_path] = (repo.repo_name, first_branch)

    bud_pattern = re.compile(r"BUD-(\d+)")

    for feat in features_by_id.values():
        title = feat["title"] or "Untitled feature"
        source_ref = feat["source_ref"]
        status = feat["feature_status"] or "implemented"

        from_bud: int | None = None
        if source_ref:
            match = bud_pattern.match(source_ref)
            if match:
                from_bud = int(match.group(1))

        # Resolve linked repos
        matched_repos: list[tuple[str, str | None]] = []
        for rp in feat["repo_paths"]:
            if rp in repo_lookup:
                matched_repos.append(repo_lookup[rp])

        all_repo_names = [rn for rn, _ in matched_repos]
        code_locs = feat["code_locations"]

        # Build per-repo code_locations mapping (repo_name → code_locs)
        repo_cl: dict[str, dict[str, list[str]]] = {
            repo_lookup[rp][0]: cl
            for rp, cl in feat["per_repo_code_locations"].items()
            if rp in repo_lookup
        }

        if matched_repos:
            # Emit one FeatureItem per linked repo
            for repo_name, branch_name in matched_repos:
                tree.features.append(
                    FeatureItem(
                        title=title,
                        status=status,
                        source_ref=source_ref,
                        branch_name=branch_name,
                        repo_name=repo_name,
                        from_bud=from_bud,
                        linked_repos=all_repo_names,
                        code_locations=code_locs,
                        repo_code_locations=repo_cl or None,
                    )
                )
        else:
            # No repo link — fallback branch from file_branch_map
            branch_name = None
            if source_ref and source_ref in file_branch_map:
                branch_name = file_branch_map[source_ref]

            tree.features.append(
                FeatureItem(
                    title=title,
                    status=status,
                    source_ref=source_ref,
                    branch_name=branch_name,
                    repo_name=None,
                    from_bud=from_bud,
                    linked_repos=[],
                    code_locations=code_locs,
                )
            )


async def _collect_bugs(
    db: AsyncSession,
    org_id: uuid.UUID,
    tree: TreeData,
) -> set[str]:
    """Collect open bugs as security threats and return bugged module names."""
    bugged_modules: set[str] = set()

    result = await db.execute(
        select(Bug)
        .where(Bug.org_id == org_id)
        .where(Bug.status.in_([BugStatus.OPEN, BugStatus.IN_PROGRESS, BugStatus.BLOCKED]))
        .order_by(Bug.created_at.desc())
        .limit(20)
    )
    for bug in result.scalars().all():
        tree.threats.append(
            SecurityThreat(
                id=str(bug.id),
                title=bug.title,
                severity=bug.severity.value if bug.severity else "medium",
                module=bug.module,
            )
        )
        if bug.module:
            bugged_modules.add(bug.module)

    return bugged_modules


async def _collect_agents(db: AsyncSession, org_id: uuid.UUID, tree: TreeData) -> None:
    """Collect agent activity for 3D visualization.

    Two queries:
      A. Active agents — PENDING/RUNNING tasks from bud_agent_tasks (what's working NOW)
      B. Recent completed — last 10 activity log events (history context)

    Each active task = one robot character in the garden. task_id is the unique key.
    """
    # ── Query A: Active agent tasks (currently working) ─────────────────────
    from sqlalchemy.orm import selectinload

    active_stmt = (
        select(BUDAgentTask)
        .options(selectinload(BUDAgentTask.bud))
        .where(
            BUDAgentTask.org_id == org_id,
            BUDAgentTask.status.in_(["pending", "running"]),
        )
        .order_by(BUDAgentTask.created_at.desc())
        .limit(20)
    )
    active_result = await db.execute(active_stmt)
    for task in active_result.scalars().all():
        # Extract impacted repo names from BUD's impacted_repos JSONB
        impacted_repos: list[str] = []
        if task.bud and task.bud.impacted_repos:
            for repo_entry in task.bud.impacted_repos:
                name = repo_entry.get("repo_name") if isinstance(repo_entry, dict) else None
                if name:
                    impacted_repos.append(name)

        tree.agent_activity.append(
            AgentActivityItem(
                agent_name=task.skill.name if task.skill else "Agent",
                action=task.status_message or f"Working on {task.task_type}...",
                timestamp=task.created_at.isoformat() if task.created_at else "",
                status=task.status or "running",
                skill_slug=task.skill.skill_slug if task.skill else "",
                repo_name=None,
                bud_number=task.bud.bud_number if task.bud else None,
                session_id=None,
                event_type="skill_invoked",
                task_id=str(task.id),
                bud_title=task.bud.title if task.bud else None,
                impacted_repo_names=impacted_repos,
            )
        )

    # ── Query B: Recent completed activity (history context) ────────────────
    completed_stmt = (
        select(
            AgentActivityLog,
            TrackedRepository.name.label("repo_name"),
            BUDDocument.bud_number.label("bud_number"),
            BUDDocument.title.label("bud_title"),
        )
        .outerjoin(TrackedRepository, AgentActivityLog.repo_id == TrackedRepository.id)
        .outerjoin(BUDDocument, AgentActivityLog.bud_id == BUDDocument.id)
        .where(
            AgentActivityLog.org_id == org_id,
            AgentActivityLog.event_type.in_(["skill_completed", "skill_failed"]),
        )
        .order_by(AgentActivityLog.created_at.desc())
        .limit(10)
    )
    result = await db.execute(completed_stmt)
    for row in result.all():
        log: AgentActivityLog = row[0]
        tree.agent_activity.append(
            AgentActivityItem(
                agent_name=log.actor_name or log.skill_slug or "agent",
                action=log.message or "",
                timestamp=log.created_at.isoformat() if log.created_at else "",
                status=log.status or "completed",
                skill_slug=log.skill_slug or "",
                repo_name=row[1],
                bud_number=row[2],
                session_id=log.session_id,
                event_type=log.event_type or "",
                task_id=str(log.task_id) if log.task_id else None,
                bud_title=row[3],
            )
        )

    # ── Fallback: Legacy AgentLog (backward compat) ─────────────────────────
    if not tree.agent_activity:
        legacy = await db.execute(
            select(AgentLog)
            .where(AgentLog.org_id == org_id)
            .order_by(AgentLog.created_at.desc())
            .limit(10)
        )
        for log in legacy.scalars().all():
            tree.agent_activity.append(
                AgentActivityItem(
                    agent_name=log.agent_name or "unknown",
                    action=log.output_summary or log.input_summary or "",
                    timestamp=log.created_at.isoformat() if log.created_at else "",
                    status=log.status or "completed",
                )
            )


async def _resolve_task_repo_name(
    db: AsyncSession, task: BUDAgentTask,
) -> str | None:
    """Resolve the primary repo name for an agent task from its activity logs."""
    stmt = (
        select(TrackedRepository.name)
        .join(AgentActivityLog, AgentActivityLog.repo_id == TrackedRepository.id)
        .where(AgentActivityLog.task_id == task.id)
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def _collect_members(db: AsyncSession, org_id: uuid.UUID, tree: TreeData) -> None:
    """Collect team members with their contribution percentages."""
    result = await db.execute(
        select(
            User.id,
            User.name,
            User.email,
            User.avatar_url,
            User.character_model,
            User.slack_id,
            func.sum(SkillProfile.touch_count).label("total_touches"),
        )
        .join(SkillProfile, SkillProfile.user_id == User.id)
        .where(SkillProfile.org_id == org_id)
        .where(User.is_active.is_(True))
        .where(~User.name.ilike("%[bot]%"))
        .group_by(
            User.id,
            User.name,
            User.email,
            User.avatar_url,
            User.character_model,
            User.slack_id,
        )
        .order_by(func.sum(SkillProfile.touch_count).desc())
        .limit(20)
    )
    rows = result.all()
    if not rows:
        return

    total_touches = sum(row.total_touches or 0 for row in rows)

    # Pre-load top 3 modules per user in a single query (avoids N+1)
    user_ids = [row.id for row in rows]
    modules_result = await db.execute(
        select(SkillProfile.user_id, SkillProfile.module, SkillProfile.skill_score)
        .where(SkillProfile.org_id == org_id)
        .where(SkillProfile.user_id.in_(user_ids))
        .order_by(SkillProfile.user_id, SkillProfile.skill_score.desc())
    )
    user_modules: dict[uuid.UUID, list[str]] = {}
    for uid, module, _score in modules_result.all():
        user_modules.setdefault(uid, [])
        if len(user_modules[uid]) < 3:
            user_modules[uid].append(module)

    for row in rows:
        touches = row.total_touches or 0
        care_pct = round((touches / total_touches * 100) if total_touches > 0 else 0, 1)
        top_modules = user_modules.get(row.id, [])

        # Look up Slack presence state
        presence = "active"
        if row.slack_id:
            presence = get_presence_state(str(org_id), row.slack_id)

        tree.members.append(
            MemberActivity(
                user_id=str(row.id),
                name=row.name or "",
                email=row.email or "",
                avatar_url=row.avatar_url,
                care_pct=care_pct,
                top_modules=top_modules,
                character_model=row.character_model,
                presence=presence,
            )
        )


def _collect_cross_repo_relationships(tree: TreeData) -> None:
    """Create inter-service arcs between repos sharing community names.

    When two repos both have a community (branch) with the same name —
    e.g. "User" in ATOACore and "User" in ATOAPayment — it signals a
    shared domain concept. We emit a synthetic IMPORTS arc so the garden
    draws a visible connection between those trees.
    """
    if len(tree.repos) < 2:
        return

    # Map community name → list of repo names that contain it
    comm_repos: dict[str, list[str]] = {}
    for repo in tree.repos:
        for branch in repo.branches:
            comm_repos.setdefault(branch.name, []).append(repo.repo_name)

    cross_count = 0
    shared_names: list[str] = []
    for comm_name, repos in comm_repos.items():
        if len(repos) < 2:
            continue
        shared_names.append(comm_name)
        # Create arcs between each pair of repos sharing this community
        for i in range(len(repos)):
            for j in range(i + 1, len(repos)):
                tree.relationships.append(
                    RelationshipArc(
                        source_branch=comm_name,
                        target_branch=comm_name,
                        source_repo=repos[i],
                        target_repo=repos[j],
                        rel_type="IMPORTS",
                        weight=3,
                    )
                )
                cross_count += 1

    logger.info(
        "cross_repo_relationships",
        count=cross_count,
        shared_communities=shared_names[:10],
        total_relationships=len(tree.relationships),
    )


async def _compute_feature_skills(
    db: AsyncSession,
    org_id: uuid.UUID,
    tree: TreeData,
) -> None:
    """Compute developer skill summaries per feature for bus-factor analysis.

    Matches developers to features by module name. For each feature, finds
    developers whose SkillProfile.module matches the feature's branch_name
    (case-insensitive substring). This works because branch names are
    top-level directory communities and skill modules are the same directories.

    Falls back to feature_id FK when available, but most profiles use module matching.
    """
    # 1. Load all skill profiles for this org (module → developers)
    result = await db.execute(
        select(
            SkillProfile.module,
            SkillProfile.user_id,
            SkillProfile.skill_score,
            SkillProfile.feature_id,
            User.name.label("dev_name"),
        )
        .join(User, User.id == SkillProfile.user_id)
        .where(SkillProfile.org_id == org_id)
        .where(SkillProfile.skill_score > 0.1)
        .where(User.is_active.is_(True))
        .order_by(SkillProfile.skill_score.desc())
    )
    rows = result.all()

    # Build module→developers and feature_id→developers lookups
    # module_lower → [(uid, name, score)]
    module_devs: dict[str, list[tuple[str, str, float]]] = {}
    for module, user_id, score, _feature_id, dev_name in rows:
        key = module.lower()
        module_devs.setdefault(key, []).append((str(user_id), dev_name, float(score)))

    # 2. For each unique feature title, find matching developers
    seen_titles: set[str] = set()
    for feat in tree.features:
        if feat.title in seen_titles:
            continue
        seen_titles.add(feat.title)

        matched: dict[str, tuple[str, float]] = {}  # uid → (name, best_score)

        # Extract keywords from feature title for matching
        # e.g. "Feature: Payment Refund Processing" → ["payment", "refund", "processing"]
        raw_title = feat.title.lower()
        # Strip "feature:" prefix if present
        if raw_title.startswith("feature:"):
            raw_title = raw_title[8:]
        title_words = [
            w for w in raw_title.split()
            if len(w) > 2 and w not in {"the", "and", "for", "with"}
        ]

        # Match by branch_name (module == branch/community name)
        if feat.branch_name:
            branch_lower = feat.branch_name.lower()
            for mod_key, devs in module_devs.items():
                if branch_lower in mod_key or mod_key in branch_lower:
                    for uid, name, score in devs:
                        if uid not in matched or score > matched[uid][1]:
                            matched[uid] = (name, score)

        # Match by title keywords against module names
        # A module matches if 2+ title keywords appear in it
        if not matched and len(title_words) >= 2:
            for mod_key, devs in module_devs.items():
                hits = sum(1 for w in title_words if w in mod_key)
                if hits >= 2:
                    for uid, name, score in devs:
                        if uid not in matched or score > matched[uid][1]:
                            matched[uid] = (name, score)

        if not matched:
            continue

        # Sort by score descending
        sorted_devs = sorted(matched.items(), key=lambda x: x[1][1], reverse=True)

        tree.feature_skills.append(
            FeatureSkillSummary(
                feature_title=feat.title,
                developer_count=len(sorted_devs),
                developers=[uid for uid, _ in sorted_devs],
                top_developer_name=sorted_devs[0][1][0] if sorted_devs else None,
            )
        )
