"""Database collectors for the Living Tree Dashboard.

Each function queries a specific domain (bugs, features, BUD stages,
agent activity, team members) and mutates the shared ``TreeData``
accumulator. All functions take an ``AsyncSession`` and ``org_id``
plus the tree; they run sequentially because the underlying
SQLAlchemy async session is not concurrency-safe.

Ordering constraints (enforced by the orchestrator in ``tree_data.py``):
  - ``collect_features`` must run BEFORE ``collect_bud_stages``
    (BUD stage items inherit branch assignment from linked features).
  - ``collect_bugs`` runs independently but BEFORE git history
    (its ``bugged_modules`` return value cross-references leaves).
"""

import re
import uuid
from typing import TypedDict

import structlog
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
    BUDItem,
    BUDStageCount,
    FeatureItem,
    MemberActivity,
    SecurityThreat,
    TreeData,
)
from app.services.org_settings import get_presence_settings
from app.services.presence_cache import get_presence_state

logger = structlog.get_logger(__name__)


# ─── Bugs ─────────────────────────────────────────────────────────────────


async def collect_bugs(
    db: AsyncSession,
    org_id: uuid.UUID,
    tree: TreeData,
) -> set[str]:
    """Collect open bugs as security threats and return bugged module names.

    Args:
        db: Async database session.
        org_id: Organization UUID.
        tree: Mutable tree accumulator (appends to ``tree.threats``).

    Returns:
        Set of module names that have open/in-progress bugs.
    """
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


# ─── Features ─────────────────────────────────────────────────────────────


class _FeatureGroup(TypedDict):
    """Intermediate grouping for multi-repo feature deduplication."""

    title: str | None
    source_ref: str | None
    feature_status: str | None
    repo_paths: list[str]
    code_locations: dict[str, list[str]]
    per_repo_code_locations: dict[str, dict[str, list[str]]]


async def collect_features(
    db: AsyncSession,
    org_id: uuid.UUID,
    tree: TreeData,
    file_branch_map: dict[str, str],
) -> None:
    """Collect features from the feature registry with BUD linkage.

    JOINs knowledge_to_repo -> tracked_repositories to resolve the repo(s)
    each feature belongs to, then maps repo_path -> first branch for placement.

    A feature linked to multiple repos via knowledge_to_repo is emitted once
    per linked repo so it appears under each repo in the graph. Features with
    no repo link are still emitted with repo_name=None.

    Args:
        db: Async database session.
        org_id: Organization UUID.
        tree: Mutable tree accumulator (appends to ``tree.features``).
        file_branch_map: File-to-branch mapping from repo_structure.
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
            features_by_id[ki_id]["code_locations"] = merge_code_locations(
                features_by_id[ki_id]["code_locations"], code_locs
            )
        if repo_path:
            features_by_id[ki_id]["repo_paths"].append(repo_path)
        if repo_path and code_locs:
            features_by_id[ki_id]["per_repo_code_locations"][repo_path] = code_locs

    tree.total_features = len(features_by_id)

    # Build a quick lookup: repo_path -> (repo_name, first_branch)
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

        matched_repos: list[tuple[str, str | None]] = []
        for rp in feat["repo_paths"]:
            if rp in repo_lookup:
                matched_repos.append(repo_lookup[rp])

        all_repo_names = [rn for rn, _ in matched_repos]
        code_locs = feat["code_locations"]

        repo_cl: dict[str, dict[str, list[str]]] = {
            repo_lookup[rp][0]: cl
            for rp, cl in feat["per_repo_code_locations"].items()
            if rp in repo_lookup
        }

        if matched_repos:
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


# ─── BUD Stages ───────────────────────────────────────────────────────────


async def collect_bud_stages(
    db: AsyncSession, org_id: uuid.UUID, tree: TreeData,
) -> None:
    """Count BUDs at each lifecycle stage and collect individual BUD items.

    Uses ``tree.features`` (already populated) to build a
    ``bud_number -> branch_name`` map so BUDs inherit the repo
    assignment of their linked feature.

    Args:
        db: Async database session.
        org_id: Organization UUID.
        tree: Mutable tree accumulator. ``tree.features`` must be
            populated before this function runs.
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

    bud_branch_map: dict[int, str] = {}
    bud_repo_map: dict[int, str] = {}
    for feat in tree.features:
        if feat.from_bud is not None:
            if feat.branch_name:
                bud_branch_map[feat.from_bud] = feat.branch_name
            if feat.repo_name:
                bud_repo_map[feat.from_bud] = feat.repo_name

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


# ─── Agents ───────────────────────────────────────────────────────────────


async def collect_agents(
    db: AsyncSession, org_id: uuid.UUID, tree: TreeData,
) -> None:
    """Collect agent activity for 3D visualization.

    Two queries:
      A. Active agents - PENDING/RUNNING tasks from bud_agent_tasks
      B. Recent completed - last 10 activity log events (history context)

    Each active task = one robot character in the garden.

    Args:
        db: Async database session.
        org_id: Organization UUID.
        tree: Mutable tree accumulator (appends to ``tree.agent_activity``).
    """
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

    # Legacy AgentLog fallback (backward compat)
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


# ─── Members ─────────────────────────────────────────────────────────────


async def collect_members(
    db: AsyncSession, org_id: uuid.UUID, tree: TreeData,
) -> None:
    """Collect ALL org members with their contribution percentages.

    Uses ``OrgToUser`` as the membership source (same as the Colyseus
    snapshot in ``internal_colyseus._collect_org_members``) so every
    member gets a house in the village — including managers and new
    joiners who haven't committed any tracked code yet. ``SkillProfile``
    is LEFT-JOINed so contribution metrics are zero instead of missing.

    Args:
        db: Async database session.
        org_id: Organization UUID.
        tree: Mutable tree accumulator (appends to ``tree.members``).
    """
    from app.models.developer_xp import DeveloperXP
    from app.models.organization import Organization
    from app.models.user import OrgToUser

    cfg_row = await db.execute(
        select(Organization.config).where(Organization.id == org_id)
    )
    presence_settings = get_presence_settings(cfg_row.scalar_one_or_none() or {})

    result = await db.execute(
        select(
            User.id,
            User.name,
            User.email,
            User.avatar_url,
            User.character_model,
            User.slack_id,
            func.coalesce(func.sum(SkillProfile.touch_count), 0).label("total_touches"),
            DeveloperXP.level,
            DeveloperXP.level_name,
        )
        # OrgToUser is the authoritative membership join — ensures every
        # org member appears regardless of contribution activity.
        .join(OrgToUser, OrgToUser.user_id == User.id)
        # LEFT JOIN SkillProfile — members without contributions get NULL
        # sums which coalesce to 0 above.
        .outerjoin(
            SkillProfile,
            (SkillProfile.user_id == User.id) & (SkillProfile.org_id == org_id),
        )
        .outerjoin(
            DeveloperXP,
            (DeveloperXP.user_id == User.id) & (DeveloperXP.org_id == org_id),
        )
        .where(OrgToUser.org_id == org_id)
        .where(User.is_active.is_(True))
        .where(~User.name.ilike("%[bot]%"))
        .group_by(
            User.id,
            User.name,
            User.email,
            User.avatar_url,
            User.character_model,
            User.slack_id,
            DeveloperXP.level,
            DeveloperXP.level_name,
        )
        # MUST match the ordering in internal_colyseus._collect_org_members
        # (ORDER BY User.id) so the housing grid slot assignment is identical
        # on frontend and server. A different ordering would place houses at
        # different grid positions than where the server positioned characters,
        # causing the "character stuck inside wrong house" bug.
        .order_by(User.id)
        .limit(50)
    )
    rows = result.all()
    if not rows:
        return

    total_touches = sum(row.total_touches or 0 for row in rows)

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

        presence = "active"
        if row.slack_id:
            presence = get_presence_state(str(org_id), row.slack_id, presence_settings)

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
                level=row.level or 1,
                level_name=row.level_name or "seedling",
            )
        )
