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

import structlog
from cachetools import TTLCache
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_log import AgentLog
from app.models.bud import BUDDocument
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

    tree = TreeData()

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


async def _collect_features(
    db: AsyncSession,
    org_id: uuid.UUID,
    tree: TreeData,
    file_branch_map: dict[str, str],
) -> None:
    """Collect features from the feature registry with BUD linkage.

    JOINs knowledge_to_repo → tracked_repositories to resolve the repo
    each feature belongs to, then maps repo_path → first branch for placement.
    """
    result = await db.execute(
        select(
            KnowledgeItem.title,
            KnowledgeItem.source_ref,
            KnowledgeItem.feature_status,
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
        .limit(200)
    )
    rows = result.all()
    tree.total_features = len(rows)

    bud_pattern = re.compile(r"BUD-(\d+)")

    for title, source_ref, feature_status, repo_path in rows:
        status = feature_status or "implemented"

        # Map repo_path → repo_name + first branch for placement
        branch_name: str | None = None
        matched_repo_name: str | None = None
        if repo_path:
            for repo in tree.repos:
                if repo.repo_path == repo_path:
                    matched_repo_name = repo.repo_name
                    if repo.branches:
                        branch_name = repo.branches[0].name
                    break

        # Fallback: try file_branch_map (rarely works but preserves old path)
        if not branch_name and source_ref and source_ref in file_branch_map:
            branch_name = file_branch_map[source_ref]

        from_bud: int | None = None
        if source_ref:
            match = bud_pattern.match(source_ref)
            if match:
                from_bud = int(match.group(1))

        tree.features.append(
            FeatureItem(
                title=title or "Untitled feature",
                status=status,
                source_ref=source_ref,
                branch_name=branch_name,
                repo_name=matched_repo_name,
                from_bud=from_bud,
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
    """Collect recent agent activity."""
    result = await db.execute(
        select(AgentLog)
        .where(AgentLog.org_id == org_id)
        .order_by(AgentLog.created_at.desc())
        .limit(10)
    )
    for log in result.scalars().all():
        tree.agent_activity.append(
            AgentActivityItem(
                agent_name=log.agent_name or "unknown",
                action=log.action or "",
                timestamp=log.created_at.isoformat() if log.created_at else "",
                status=log.status or "completed",
            )
        )


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

    for row in rows:
        touches = row.total_touches or 0
        care_pct = round((touches / total_touches * 100) if total_touches > 0 else 0, 1)

        modules_result = await db.execute(
            select(SkillProfile.module)
            .where(SkillProfile.user_id == row.id)
            .where(SkillProfile.org_id == org_id)
            .order_by(SkillProfile.skill_score.desc())
            .limit(3)
        )
        top_modules = [m for (m,) in modules_result.all()]

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
