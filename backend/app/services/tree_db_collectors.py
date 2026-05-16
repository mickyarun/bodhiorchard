# Copyright 2025-2026 Arun Rajkumar
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

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
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.agent_activity import AgentActivityLogRepository
from app.repositories.bud import BUDRepository
from app.repositories.bud_agent_task import BUDAgentTaskRepository
from app.repositories.bug import BugRepository
from app.repositories.feature_reads import FeatureReadRepository
from app.repositories.organization import OrganizationRepository
from app.repositories.skill_profile import SkillProfileRepository
from app.repositories.user import UserRepository
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
from app.utils.code_locations import merge_code_locations

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

    bugs = await BugRepository(db, org_id=org_id).list_recent_open(limit=20)
    for bug in bugs:
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

    JOINs PRIMARY ``feature_to_repo`` rows -> tracked_repositories to
    resolve the source repo for each feature, then maps repo_path ->
    first branch for placement. Features with no PRIMARY junction
    (BUD-authored) are emitted once with repo_name=None.

    Args:
        db: Async database session.
        org_id: Organization UUID.
        tree: Mutable tree accumulator (appends to ``tree.features``).
        file_branch_map: File-to-branch mapping from repo_structure.
    """
    feature_reads = FeatureReadRepository(db, org_id=org_id)
    rows = await feature_reads.list_features_with_repo_paths()

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

    backend_names_by_feature = await feature_reads.backend_repo_names_for_features(
        list(features_by_id.keys())
    )

    # Build a quick lookup: repo_path -> (repo_name, first_branch)
    repo_lookup: dict[str, tuple[str, str | None]] = {}
    # Inverse keyed by name — used to place "backend-shadow" feature items
    # under linked backend repos (the graph view detects cross-repo by
    # spotting feature nodes that share a title across repos).
    branch_by_repo_name: dict[str, str | None] = {}
    for repo in tree.repos:
        first_branch = repo.branches[0].name if repo.branches else None
        repo_lookup[repo.repo_path] = (repo.repo_name, first_branch)
        branch_by_repo_name[repo.repo_name] = first_branch

    bud_pattern = re.compile(r"BUD-(\d+)")

    for fid, feat in features_by_id.items():
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

        primary_repo_names = [rn for rn, _ in matched_repos]
        # Primary first, then backend repos not already present — preserves
        # "this feature lives here" as the lead name while still surfacing
        # cross-repo dependencies for the arc renderer.
        seen = set(primary_repo_names)
        backend_extras = [rn for rn in backend_names_by_feature.get(fid, []) if rn not in seen]
        all_repo_names = primary_repo_names + backend_extras
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
                        link_role="primary",
                    )
                )
            # Backend-shadow items: one extra FeatureItem per linked backend
            # repo so the graph view's duplicate-title detector creates an
            # arc to the backend node. code_locations are left empty because
            # the source files don't live there — only the matched routes
            # (which the graph doesn't render today) do. Per-repo consumers
            # filter on ``link_role == "primary"`` to avoid double-counting.
            for backend_name in backend_extras:
                if backend_name not in branch_by_repo_name:
                    continue
                tree.features.append(
                    FeatureItem(
                        title=title,
                        status=status,
                        source_ref=source_ref,
                        branch_name=branch_by_repo_name[backend_name],
                        repo_name=backend_name,
                        from_bud=from_bud,
                        linked_repos=all_repo_names,
                        code_locations=None,
                        repo_code_locations=None,
                        link_role="backend",
                    )
                )
        elif backend_extras:
            # PRIMARY repo exists in the DB but is not in ``repo_lookup``
            # (untracked / inactive). Surface the feature anyway by
            # treating the first reachable backend as the synthetic
            # primary so the arc renderer still has 2+ entries to connect.
            placeholder_repos = [b for b in backend_extras if b in branch_by_repo_name]
            for backend_name in placeholder_repos:
                tree.features.append(
                    FeatureItem(
                        title=title,
                        status=status,
                        source_ref=source_ref,
                        branch_name=branch_by_repo_name[backend_name],
                        repo_name=backend_name,
                        from_bud=from_bud,
                        linked_repos=placeholder_repos,
                        code_locations=None,
                        repo_code_locations=None,
                        link_role="backend",
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
    db: AsyncSession,
    org_id: uuid.UUID,
    tree: TreeData,
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
    bud_repo = BUDRepository(db, org_id=org_id)
    status_counts = await bud_repo.count_by_status_grouped()
    counts = BUDStageCount()
    for status_val, count in status_counts.items():
        status_str = status_val.value if hasattr(status_val, "value") else str(status_val)
        if hasattr(counts, status_str):
            setattr(counts, status_str, count)
    tree.bud_stages = counts

    bud_branch_map: dict[int, str] = {}
    bud_repo_map: dict[int, str] = {}
    # ``setdefault`` so the first row wins — the collector appends primary
    # repos before backend-shadow rows for the same feature, and we want
    # the primary repo/branch in the BUD summary, not the backend it links.
    for feat in tree.features:
        if feat.from_bud is not None:
            if feat.branch_name:
                bud_branch_map.setdefault(feat.from_bud, feat.branch_name)
            if feat.repo_name:
                bud_repo_map.setdefault(feat.from_bud, feat.repo_name)

    summary_rows = await bud_repo.list_summaries_in_statuses(
        ["testing", "uat", "prod", "closed"], limit=50
    )
    for bud_number, title, status_val in summary_rows:
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
    db: AsyncSession,
    org_id: uuid.UUID,
    tree: TreeData,
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
    active_tasks = await BUDAgentTaskRepository(db, org_id=org_id).list_active_with_bud(limit=20)
    for task in active_tasks:
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

    completed_rows = await AgentActivityLogRepository(db, org_id=org_id).list_recent_with_repo_bud(
        ["skill_completed", "skill_failed"], limit=10
    )
    for log, repo_name, bud_number, bud_title in completed_rows:
        tree.agent_activity.append(
            AgentActivityItem(
                agent_name=log.actor_name or log.skill_slug or "agent",
                action=log.message or "",
                timestamp=log.created_at.isoformat() if log.created_at else "",
                status=log.status or "completed",
                skill_slug=log.skill_slug or "",
                repo_name=repo_name,
                bud_number=bud_number,
                session_id=log.session_id,
                event_type=log.event_type or "",
                task_id=str(log.task_id) if log.task_id else None,
                bud_title=bud_title,
            )
        )


# ─── Members ─────────────────────────────────────────────────────────────


async def collect_members(
    db: AsyncSession,
    org_id: uuid.UUID,
    tree: TreeData,
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
    org_config = await OrganizationRepository(db).get_config(org_id) or {}
    presence_settings = get_presence_settings(org_config)

    rows = await UserRepository(db).list_active_members_for_tree(org_id, limit=50)
    if not rows:
        return

    total_touches = sum(row.total_touches or 0 for row in rows)

    user_ids = [row.id for row in rows]
    module_rows = await SkillProfileRepository(db, org_id=org_id).list_modules_for_users(user_ids)
    user_modules: dict[uuid.UUID, list[str]] = {}
    for uid, module, _score in module_rows:
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
                house_level=row.house_level or 1,
            )
        )
