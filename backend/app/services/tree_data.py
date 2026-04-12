"""Tree data aggregation service for the Living Tree Dashboard.

Orchestrates data collection from git history, BUDs, bugs, agent logs,
and member profiles to build the ``TreeData`` response. The actual
collection logic lives in focused sub-modules:

  ``tree_repo_structure``  — branch discovery from git working tree
  ``tree_git_metrics``     — commit history, evergreen colors, health scoring
  ``tree_db_collectors``   — bugs, features, BUD stages, agents, members
  ``tree_relationships``   — cross-repo relationship arcs
  ``tree_skill_analysis``  — per-feature developer skill / bus-factor

Architecture:
  - Trunk = organization
  - Limbs = tracked repositories (RepoLimbData)
  - Branches = top-level directories within each repo
  - Leaves = recently committed files (evergreen color model)
"""

import uuid

import structlog
from cachetools import TTLCache
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.dashboard import TreeData
from app.services.tree_db_collectors import (
    collect_agents,
    collect_bud_stages,
    collect_bugs,
    collect_features,
    collect_members,
)
from app.services.tree_git_metrics import classify_repo_growth_stage, collect_git_history
from app.services.tree_relationships import collect_cross_repo_relationships
from app.services.tree_repo_structure import collect_repo_structure
from app.services.tree_skill_analysis import compute_feature_skills

logger = structlog.get_logger(__name__)

# TTL cache: one entry per org, 5-minute expiry
_cache: TTLCache[str, TreeData] = TTLCache(maxsize=64, ttl=300)


async def get_tree_data(
    db: AsyncSession,
    org_id: uuid.UUID,
    tracked_repos: list[tuple[str, str]],
    *,
    refresh: bool = False,
) -> TreeData:
    """Build the complete TreeData for the Living Tree dashboard.

    Coordinates all collection phases in the correct dependency order:
      1. Repo structure  → file_branch_map (consumed by git history + features)
      2. Bugs            → bugged_modules set (consumed by git history)
      3. Git history     → leaves, health, branch stats
      4. Growth stage    → per-repo classification
      5. Features        → must run before bud_stages (produces bud→branch map)
      6. BUD stages      → depends on features
      7. Agents          → independent
      8. Members         → independent
      9. Cross-repo arcs → depends on repo structure
     10. Feature skills  → depends on features

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

    # 1. Repo structure → file_branch_map
    file_branch_map = await collect_repo_structure(tree, tracked_repos)

    # 2. Bugs (before git history for cross-reference)
    bugged_modules = await collect_bugs(db, org_id, tree)

    # 3. Git history with evergreen colors + bug cross-ref
    await collect_git_history(tree, tracked_repos, file_branch_map, bugged_modules)

    # 4. Growth stage classification
    for repo_limb in tree.repos:
        repo_limb.growth_stage = classify_repo_growth_stage(repo_limb)

    # 5-8. DB queries (AsyncSession is not concurrency-safe)
    # Features first: builds the bud→branch map needed by collect_bud_stages
    await collect_features(db, org_id, tree, file_branch_map)
    await collect_bud_stages(db, org_id, tree)
    await collect_agents(db, org_id, tree)
    await collect_members(db, org_id, tree)

    # 9. Flatten branches for backward compatibility
    tree.branches = []
    for repo_limb in tree.repos:
        tree.branches.extend(repo_limb.branches)

    # 10. Cross-repo relationship arcs
    collect_cross_repo_relationships(tree)

    # 11. Feature skill summaries (bus factor)
    await compute_feature_skills(db, org_id, tree)

    _cache[cache_key] = tree
    return tree
