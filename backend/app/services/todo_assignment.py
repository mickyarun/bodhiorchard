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

"""Default TODO assignment on DEVELOPMENT entry.

On DEVELOPMENT entry the BUD's phase lead (chosen by smart assignment)
owns every TODO. Other developers can pick up individual items via the
Claim UI or the MCP ``takeover_todo`` tool — that is the only way a
TODO transfers hands.

When the org has Teams mapped to repos, ``assign_todos_per_repo_team``
splits per-repo TODOs across the repo's owning team developers via
least-loaded round-robin. TODOs without a ``repo_name``, and repos
with no owning team, fall back to the BUD lead — same behaviour the
codebase had before teams existed.
"""

import uuid
from collections import defaultdict

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bud_todo import BUDTodo
from app.models.user import UserRole
from app.repositories.bud import BUDRepository
from app.repositories.bud_todo import BUDTodoRepository
from app.repositories.team import TeamRepository
from app.repositories.tracked_repository import TrackedRepoRepository
from app.repositories.user import UserRepository
from app.services.assignment_policy import TERMINAL_BUD_STATUSES
from app.services.event_bus import publish

logger = structlog.get_logger(__name__)


async def assign_all_todos_to_lead(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud_id: uuid.UUID,
    lead_user_id: uuid.UUID,
) -> int:
    """Assign every unassigned non-checkpoint TODO to the phase lead.

    Preserves the existing single-owner-per-BUD mental model. Other
    developers can self-assign individual TODOs afterwards via the UI
    or MCP ``takeover_todo``.

    Returns the number of TODOs newly assigned.
    """
    unassigned = await _list_unassigned_non_checkpoint_todos(db, org_id, bud_id)
    if not unassigned:
        return 0

    for todo in unassigned:
        todo.assignee_id = lead_user_id

    await db.flush()
    logger.info(
        "todo_assigned_to_lead",
        bud_id=str(bud_id),
        lead_user_id=str(lead_user_id),
        assigned=len(unassigned),
    )
    return len(unassigned)


async def _list_unassigned_non_checkpoint_todos(
    db: AsyncSession, org_id: uuid.UUID, bud_id: uuid.UUID
) -> list[BUDTodo]:
    return await BUDTodoRepository(db, org_id=org_id).list_unassigned_non_checkpoint_for_bud(
        bud_id
    )


async def assign_todos_per_repo_team(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud_id: uuid.UUID,
    lead_user_id: uuid.UUID,
) -> dict[str, int]:
    """Per-repo TODO assignment that respects team-repo ownership.

    Behaviour per TODO:

    - TODO has no ``repo_name`` → assigned to ``lead_user_id``.
    - ``repo_name`` doesn't resolve to a tracked repo → assigned to
      lead, with a warning log so the admin sees the mismatch.
    - Repo found but no team owns it, or no DEVELOPER member of an
      owning team is active → assigned to lead, same warning.
    - Repo + owning-team DEVELOPER members present → least-loaded
      round-robin among them across the TODOs for that repo (so a
      BUD touching one repo with 5 TODOs distributes them rather
      than dumping all on the first dev picked).

    Returns a dict of buckets: ``{"team_scoped", "lead_fallback",
    "no_repo_match", "no_team", "no_dev_in_team", "skipped_no_repo_name"}``
    so the caller / test can assert how the split landed. Total of all
    bucket values equals the number of unassigned TODOs found.

    Failure of any single lookup never crashes the whole pass —
    affected TODOs degrade to ``lead_user_id`` and a warning fires.
    Mass DB errors still propagate (we want the PATCH to retry
    rather than ship a half-assigned BUD).
    """
    unassigned = await _list_unassigned_non_checkpoint_todos(db, org_id, bud_id)
    if not unassigned:
        return {
            "team_scoped": 0,
            "lead_fallback": 0,
            "no_repo_match": 0,
            "no_team": 0,
            "no_dev_in_team": 0,
            "skipped_no_repo_name": 0,
        }

    buckets: dict[str, int] = defaultdict(int)
    by_repo: dict[str | None, list[BUDTodo]] = defaultdict(list)
    for t in unassigned:
        by_repo[t.repo_name].append(t)

    repo_repo = TrackedRepoRepository(db, org_id=org_id)
    team_repo = TeamRepository(db, org_id=org_id)
    user_repo = UserRepository(db)
    bud_repo = BUDRepository(db, org_id=org_id)

    developer_pool = await user_repo.list_active_with_role(org_id, UserRole.DEVELOPER)
    developer_ids = {u.id for u in developer_pool}

    for repo_name, todos in by_repo.items():
        if not repo_name:
            for t in todos:
                t.assignee_id = lead_user_id
                buckets["skipped_no_repo_name"] += 1
            continue

        repo = await repo_repo.get_by_name(repo_name)
        if repo is None:
            logger.warning(
                "todo_per_repo_no_tracked_repo",
                bud_id=str(bud_id),
                repo_name=repo_name,
                count=len(todos),
            )
            for t in todos:
                t.assignee_id = lead_user_id
            buckets["no_repo_match"] += len(todos)
            continue

        team_user_ids = await team_repo.list_member_ids_for_repos([repo.id])
        eligible_ids = team_user_ids & developer_ids
        if not eligible_ids:
            bucket = "no_team" if not team_user_ids else "no_dev_in_team"
            logger.warning(
                f"todo_per_repo_{bucket}",
                bud_id=str(bud_id),
                repo_name=repo_name,
                repo_id=str(repo.id),
                count=len(todos),
            )
            for t in todos:
                t.assignee_id = lead_user_id
            buckets[bucket] += len(todos)
            continue

        load_map = await bud_repo.count_active_loads_for_assignees(
            list(eligible_ids), [s.value for s in TERMINAL_BUD_STATUSES]
        )
        # Sort eligible by current load (ascending) once, then
        # round-robin through them across this repo's TODOs so a
        # 5-TODO repo with 2 devs splits 3/2 rather than 5/0.
        eligible_ordered = sorted(eligible_ids, key=lambda uid: (load_map.get(uid, 0), str(uid)))
        for idx, t in enumerate(todos):
            t.assignee_id = eligible_ordered[idx % len(eligible_ordered)]
            buckets["team_scoped"] += 1

    await db.flush()

    buckets["lead_fallback"] = (
        buckets["skipped_no_repo_name"]
        + buckets["no_repo_match"]
        + buckets["no_team"]
        + buckets["no_dev_in_team"]
    )

    logger.info(
        "todo_assigned_per_repo_team",
        bud_id=str(bud_id),
        lead_user_id=str(lead_user_id),
        **buckets,
    )

    publish(
        f"todo:{bud_id}",
        {
            "event": "todos_per_repo_assigned",
            "bud_id": str(bud_id),
            "team_scoped": buckets["team_scoped"],
            "lead_fallback": buckets["lead_fallback"],
        },
    )
    return dict(buckets)


async def cascade_assignee_to_todos(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud_id: uuid.UUID,
    new_assignee_id: uuid.UUID,
) -> int:
    """Mirror a manual top-level BUD reassignment onto its TODOs.

    Only touches ``assignee_id`` — never status. Aborts (returns ``-1``)
    if any non-checkpoint TODO is in_progress, completed, or has been
    taken over (``taken_at IS NOT NULL``); we never overwrite a
    developer's claim with a top-level reassignment. Returns the count
    of TODOs whose assignee changed when the cascade ran.

    Caller is responsible for restricting this to DEVELOPMENT phase —
    other phases don't have per-TODO ownership semantics yet.
    """
    repo = BUDTodoRepository(db, org_id=org_id)
    if await repo.has_active_or_taken_todos(bud_id):
        logger.info(
            "todo_cascade_skipped_work_in_progress",
            bud_id=str(bud_id),
            new_assignee_id=str(new_assignee_id),
        )
        return -1

    todos = await repo.list_non_checkpoint_for_bud(bud_id)
    changed = 0
    for todo in todos:
        if todo.assignee_id != new_assignee_id:
            todo.assignee_id = new_assignee_id
            changed += 1

    if changed:
        await db.flush()
        # Publish before commit, mirroring the ``todo_claimed`` path in
        # ``api/v1/bud_todos.py``. If the outer transaction later rolls
        # back, the worst case is a redundant refetch from the frontend
        # that re-reads the unchanged DB state — no consistency risk
        # because every subscriber re-queries the source of truth.
        publish(
            f"todo:{bud_id}",
            {
                "event": "assignee_cascaded",
                "bud_id": str(bud_id),
                "new_assignee_id": str(new_assignee_id),
                "changed_count": changed,
            },
        )
    logger.info(
        "todo_cascade_assigned",
        bud_id=str(bud_id),
        new_assignee_id=str(new_assignee_id),
        changed=changed,
    )
    return changed
