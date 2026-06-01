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

"""Contributor breakdown + parallelism score for the post-close Learning Agent.

For each user who touched the BUD (commits, PRs, TODOs), counts the
work they did and derives a "who's dragging velocity" signal. The
parallelism score is a single 0-1 float: the fraction of dev-day
buckets inside the DEVELOPMENT phase window where ≥ 2 distinct users
committed.
"""

import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bud import BUDDocument, BUDStatus
from app.models.bud_todo import BUDTodoStatus
from app.models.pull_request import PRState
from app.repositories.bud_todo import BUDTodoRepository
from app.repositories.dev_activity import DevActivityLogRepository
from app.repositories.pull_request import PullRequestRepository
from app.repositories.user import UserRepository
from app.services.contributor_resolver import get_bud_contributors


def _date_bucket(ts: datetime) -> str:
    """ISO date (YYYY-MM-DD) for grouping commits into day buckets."""
    return ts.date().isoformat()


async def build_contributor_breakdown(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud: BUDDocument,
) -> list[dict[str, Any]]:
    """Per-contributor commits / PRs merged / TODOs completed / active days.

    Contributors are identified two ways:
    - ``user_id``: internal team members. Seeded from
      ``contributor_resolver.get_bud_contributors`` (the same union
      used by stage-XP awards) and matched against dev_activity rows,
      PR ``author_user_id``, and BUDTodo ``assignee_id``.
    - ``github_login``: external collaborators whose PRs are linked
      to the BUD but who don't have a local users row yet. The PR
      counts toward the BUD's learning recap under their GitHub
      identity so the work isn't silently dropped just because the
      author was never on-boarded.

    The returned dicts always carry ``user_id`` (UUID string or None)
    and ``github_login`` (the GitHub handle, or None for purely-internal
    contributors). Sort order is commits desc, then prs_merged desc,
    so internal contributors with code-level activity rank ahead of
    PR-only external collaborators.
    """
    user_ids = await get_bud_contributors(db, org_id, bud.id)
    commits = await DevActivityLogRepository(db, org_id=org_id).list_commit_tuples_for_bud(bud.id)
    prs = await PullRequestRepository(db, org_id=org_id).list_for_bud(bud.id)
    todos = await BUDTodoRepository(db, org_id=org_id).list_for_bud(bud.id)
    users = await UserRepository(db).get_many_by_ids(list(user_ids)) if user_ids else []
    name_by_id = {u.id: u.name or u.email for u in users}

    per_user_commits: dict[uuid.UUID, set[str]] = {uid: set() for uid in user_ids}
    per_user_days: dict[uuid.UUID, set[str]] = {uid: set() for uid in user_ids}
    for uid, sha, created_at in commits:
        if uid is None or uid not in per_user_commits or sha is None:
            continue
        per_user_commits[uid].add(sha)
        per_user_days[uid].add(_date_bucket(created_at))

    per_user_prs: dict[uuid.UUID, int] = {uid: 0 for uid in user_ids}
    per_user_todos: dict[uuid.UUID, int] = {uid: 0 for uid in user_ids}
    # External-author PR counts keyed by github_login. Only PRs whose
    # author_user_id couldn't be resolved land here; resolved authors
    # roll into per_user_prs above.
    per_login_prs: dict[str, int] = {}

    for pr in prs:
        if pr.state != PRState.MERGED:
            continue
        if pr.author_user_id is not None and pr.author_user_id in per_user_prs:
            per_user_prs[pr.author_user_id] += 1
            continue
        login = (pr.author_github_login or "").strip()
        if login:
            per_login_prs[login] = per_login_prs.get(login, 0) + 1

    for todo in todos:
        if todo.assignee_id in per_user_todos and todo.status == BUDTodoStatus.COMPLETED.value:
            per_user_todos[todo.assignee_id] += 1

    out: list[dict[str, Any]] = []
    for uid in user_ids:
        out.append(
            {
                "user_id": str(uid),
                "github_login": None,
                "name": name_by_id.get(uid) or "(unknown)",
                "commits": len(per_user_commits[uid]),
                "prs_merged": per_user_prs[uid],
                "todos_completed": per_user_todos[uid],
                "active_days": len(per_user_days[uid]),
            }
        )
    for login, count in per_login_prs.items():
        out.append(
            {
                "user_id": None,
                "github_login": login,
                "name": f"{login} (external)",
                "commits": 0,
                "prs_merged": count,
                "todos_completed": 0,
                "active_days": 0,
            }
        )
    out.sort(key=lambda r: (r["commits"], r["prs_merged"]), reverse=True)
    return out


async def compute_parallelism_score(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud: BUDDocument,
    phase_metrics: dict[str, dict[str, Any]],
) -> float | None:
    """Fraction of DEVELOPMENT dev-day buckets with ≥2 distinct committers.

    Returns None when DEVELOPMENT wasn't entered or no commits landed in
    the window — there's no signal to report and emitting 0.0 would
    falsely imply "purely solo work" when the truth is "no commit data".
    """
    dev_window = phase_metrics.get(BUDStatus.DEVELOPMENT.value)
    if not dev_window:
        return None
    entered_at = dev_window.get("entered_at")
    exited_at = dev_window.get("exited_at")
    if not entered_at or not exited_at:
        return None
    entry_dt = datetime.fromisoformat(entered_at)
    exit_dt = datetime.fromisoformat(exited_at)
    if exit_dt <= entry_dt:
        return None

    commits = await DevActivityLogRepository(db, org_id=org_id).list_commit_tuples_for_bud(bud.id)
    users_per_day: dict[str, set[uuid.UUID]] = {}
    for uid, _sha, ts in commits:
        if uid is None:
            continue
        if not (entry_dt <= ts <= exit_dt):
            continue
        users_per_day.setdefault(_date_bucket(ts), set()).add(uid)

    if not users_per_day:
        return None

    # Denominator: every calendar day in the window, including the ones
    # with no commits. A team that committed 1 day a week shouldn't get a
    # parallelism score of 1.0 just because that one day had 2 committers
    # — the silence between commits is part of the velocity picture.
    total_days = max(1, (exit_dt.date() - entry_dt.date()).days + 1)
    parallel_days = sum(1 for users in users_per_day.values() if len(users) >= 2)
    return round(parallel_days / total_days, 3)


# A separate alias the orchestrator imports so it can stay symmetric with
# ``build_phase_metrics`` / ``build_contributor_breakdown`` even though
# parallelism is a single number rather than a structured dict.
build_parallelism_score = compute_parallelism_score


def cycle_time_days(bud: BUDDocument, bud_closed_at: datetime) -> float | None:
    """Wall-clock days from BUD creation to close, or None if both timestamps missing."""
    if bud.created_at is None:
        return None
    delta: timedelta = bud_closed_at - bud.created_at
    if delta.total_seconds() < 0:
        return 0.0
    return round(delta.total_seconds() / 86_400.0, 3)
