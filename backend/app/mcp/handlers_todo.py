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

"""MCP handlers for BUD TODO plan delivery.

Three tools:

- ``get_bud_plan`` — returns the BUD's architecture + TODOs filtered
  for the requesting developer. TODO titles are visible to all; per-TODO
  implementation details are gated behind ``takeover_todo``.

- ``takeover_todo`` — atomically claim a pending TODO and move it to
  ``in_progress``. Returns the full ``context_md`` only on success.
  Claude Code MUST call this before implementing any TODO.

- ``complete_todo`` — mark an ``in_progress`` TODO as completed, with
  a short summary of what was done (visible to other developers).
"""

import uuid
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.mcp.auth import MCPAuthResult
from app.mcp.handler_utils import require_non_empty
from app.models.bud_todo import BUDTodo, BUDTodoStatus
from app.repositories.bud import BUDRepository
from app.repositories.bud_todo import BUDTodoRepository
from app.repositories.dev_activity import DevActivityLogRepository
from app.repositories.pull_request import PullRequestRepository
from app.services.bud_timeline import record_event
from app.services.event_bus import publish
from app.services.pr_auto_transition import check_all_repos_have_prs

logger = structlog.get_logger(__name__)


# ── Tool: get_bud_plan ─────────────────────────────────────────────


async def handle_get_bud_plan(
    db: AsyncSession,
    auth: MCPAuthResult,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Return the BUD plan with TODOs marked yours/skip for the caller.

    Per the information-gating rule, this tool DOES NOT return the
    per-TODO ``context_md``. Claude Code must call ``takeover_todo``
    to receive the implementation details for a specific item.
    """
    bud_number = params.get("bud_number")
    if bud_number is None:
        return {"success": False, "error": "bud_number is required"}

    user_id = auth.user.id if auth.user else None

    bud_repo = BUDRepository(db, org_id=auth.org.id)
    bud = await bud_repo.get_by_number(int(bud_number))
    if bud is None:
        return {"success": False, "error": f"BUD-{int(bud_number):03d} not found"}

    todo_repo = BUDTodoRepository(db, org_id=auth.org.id)
    todos = await todo_repo.list_for_bud(bud.id)

    your_seqs = [t.sequence for t in todos if not t.is_checkpoint and t.assignee_id == user_id]
    skip_seqs = [
        t.sequence for t in todos if not t.is_checkpoint and t.assignee_id not in (user_id, None)
    ]

    other_branches = await _collect_other_branches(
        db, auth.org.id, bud.id, bud.bud_number, user_id
    )

    return {
        "success": True,
        "bud_number": bud.bud_number,
        "title": bud.title,
        "tech_spec_md": bud.tech_spec_md or "",
        "todos": [_to_summary(t, user_id) for t in todos],
        "your_todos": your_seqs,
        "skip_todos": skip_seqs,
        "instructions": _build_instructions(your_seqs, skip_seqs),
        "other_branches": other_branches,
    }


def _to_summary(todo: BUDTodo, user_id: uuid.UUID | None) -> dict[str, Any]:
    """Public TODO summary — NO context_md (gated by takeover_todo)."""
    is_yours = bool(user_id) and todo.assignee_id == user_id
    return {
        "sequence": todo.sequence,
        "title": todo.title,
        "status": todo.status,
        "is_checkpoint": todo.is_checkpoint,
        "yours": is_yours,
        "skip": (not is_yours) and not todo.is_checkpoint and todo.assignee_id is not None,
        "assignee_name": todo.assignee.name if todo.assignee else None,
        "summary": todo.summary,
    }


def _build_instructions(your_seqs: list[int], skip_seqs: list[int]) -> str:
    """Build a one-line instruction string for Claude."""
    if not your_seqs:
        return (
            "No TODOs are assigned to you for this BUD. "
            "Contact your team lead or the BUD owner before implementing anything."
        )
    your_str = ", ".join(f"#{s}" for s in your_seqs)
    if skip_seqs:
        skip_str = ", ".join(f"#{s}" for s in skip_seqs)
        return (
            f"Implement TODOs {your_str}. Skip {skip_str} (assigned to other "
            "developers). Call takeover_todo before starting each TODO."
        )
    return f"Implement TODOs {your_str}. Call takeover_todo before starting each TODO."


# ── Tool: takeover_todo ────────────────────────────────────────────


async def handle_takeover_todo(
    db: AsyncSession,
    auth: MCPAuthResult,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Atomically claim a pending TODO and return its context.

    This is the ONLY tool that returns per-TODO ``context_md`` —
    Claude must hold a claimed TODO before implementing.
    """
    if auth.user is None:
        return {
            "success": False,
            "error": "takeover_todo requires a per-user MCP token",
        }

    error = require_non_empty(params, "bud_number", "sequence")
    if error:
        return error
    bud_number = params["bud_number"]
    sequence = params["sequence"]

    bud_repo = BUDRepository(db, org_id=auth.org.id)
    bud = await bud_repo.get_by_number(int(bud_number))
    if bud is None:
        return {"success": False, "error": f"BUD-{int(bud_number):03d} not found"}

    todo_repo = BUDTodoRepository(db, org_id=auth.org.id)
    claimed = await todo_repo.atomic_takeover(bud.id, int(sequence), auth.user.id)
    if claimed is None:
        # Race lost or wrong state — fetch the current record to build an
        # informative error.
        existing = await todo_repo.get_by_sequence(bud.id, int(sequence))
        if existing is None:
            return {"success": False, "error": f"TODO #{sequence} not found"}
        if existing.is_checkpoint:
            return {
                "success": False,
                "error": f"TODO #{sequence} is a code-review checkpoint, not implementation work.",
            }
        holder = existing.assignee.name if existing.assignee else "another developer"
        return {
            "success": False,
            "error": (
                f"TODO #{sequence} is already {existing.status} "
                f"(held by {holder}). Skip it and pick another."
            ),
        }

    await record_event(
        db,
        auth.org.id,
        bud.id,
        "todo_taken_over",
        actor_id=auth.user.id,
        actor_name=auth.user.name,
        detail={"todo_id": str(claimed.id), "sequence": claimed.sequence},
    )
    publish(
        f"todo:{bud.id}",
        {
            "event": "taken_over",
            "todo_id": str(claimed.id),
            "sequence": claimed.sequence,
            "claimed_by_id": str(auth.user.id),
            "claimed_by_name": auth.user.name,
        },
    )

    return {
        "success": True,
        "todo": {
            "sequence": claimed.sequence,
            "title": claimed.title,
            "context_md": claimed.context_md,
            "phase": claimed.phase,
        },
        "guidance": (
            "You may now implement this TODO. Call complete_todo when done. "
            "Do NOT implement any other TODO without calling takeover_todo for it first."
        ),
    }


# ── Tool: complete_todo ────────────────────────────────────────────


async def handle_complete_todo(
    db: AsyncSession,
    auth: MCPAuthResult,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Mark an in_progress TODO as completed with a summary.

    Only the current assignee may complete. Summary is stored on the
    TODO and surfaced to other developers via ``get_bud_plan``.
    """
    if auth.user is None:
        return {
            "success": False,
            "error": "complete_todo requires a per-user MCP token",
        }

    error = require_non_empty(params, "bud_number", "sequence", "summary")
    if error:
        return error
    bud_number = params["bud_number"]
    sequence = params["sequence"]
    summary = params["summary"].strip()

    bud_repo = BUDRepository(db, org_id=auth.org.id)
    bud = await bud_repo.get_by_number(int(bud_number))
    if bud is None:
        return {"success": False, "error": f"BUD-{int(bud_number):03d} not found"}

    todo_repo = BUDTodoRepository(db, org_id=auth.org.id)
    todo = await todo_repo.get_by_sequence(bud.id, int(sequence))
    if todo is None:
        return {"success": False, "error": f"TODO #{sequence} not found"}
    if todo.assignee_id != auth.user.id:
        return {
            "success": False,
            "error": f"TODO #{sequence} is not assigned to you — cannot complete.",
        }
    if todo.status != BUDTodoStatus.IN_PROGRESS.value:
        return {
            "success": False,
            "error": f"TODO #{sequence} is {todo.status}, not in_progress.",
        }

    todo.status = BUDTodoStatus.COMPLETED.value
    todo.summary = summary[:4000]
    await db.flush()

    await record_event(
        db,
        auth.org.id,
        bud.id,
        "todo_completed",
        actor_id=auth.user.id,
        actor_name=auth.user.name,
        detail={
            "todo_id": str(todo.id),
            "sequence": todo.sequence,
            "summary": todo.summary,
        },
    )
    publish(
        f"todo:{bud.id}",
        {
            "event": "completed",
            "todo_id": str(todo.id),
            "sequence": todo.sequence,
            "summary": todo.summary,
            "completed_by_id": str(auth.user.id),
            "completed_by_name": auth.user.name,
        },
    )

    remaining = await _count_remaining_todos(db, auth.org.id, bud.id)

    # If this completion clears the TODO gate AND the BUD is still in
    # development, the dev → code_review transition may now be eligible
    # (PR-opened webhook may have already fired with TODOs pending and
    # been deflected by ``check_all_repos_have_prs``'s gate). Re-running
    # that check here is the natural trigger for "last TODO ticked off
    # AFTER the PRs were already raised" — without it the BUD would
    # stall in development indefinitely. The function is a no-op when
    # the gate or any other precondition isn't met.
    await check_all_repos_have_prs(db, auth.org.id, bud)

    return {"success": True, "remaining": remaining}


async def _count_remaining_todos(db: AsyncSession, org_id: uuid.UUID, bud_id: uuid.UUID) -> int:
    return await BUDTodoRepository(db, org_id=org_id).count_remaining_for_bud(bud_id)


# ── Cross-branch context for get_bud_plan ──────────────────────────


async def _collect_other_branches(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud_id: uuid.UUID,
    bud_number: int,
    current_user_id: uuid.UUID | None,
) -> list[dict[str, Any]]:
    """Summarise what other developers have done on this BUD.

    Uses ``DevActivityLog`` (branches + files) and ``PullRequest`` (PR
    metadata) — both already indexed by ``bud_id``. Returns a lightweight
    summary so Claude can decide whether to ``git diff`` another branch.
    """
    branch_info: dict[str, dict[str, Any]] = {}

    activity_repo = DevActivityLogRepository(db, org_id=org_id)
    activity = await activity_repo.list_recent_branch_activity_for_bud(bud_id)
    for branch, actor_name, user_id, files_changed in activity:
        if user_id == current_user_id:
            continue
        if not branch or not branch.startswith(f"bud-{bud_number:03d}"):
            continue
        entry = branch_info.setdefault(
            branch, {"branch": branch, "developer": actor_name, "recent_files": set()}
        )
        if files_changed:
            for path in files_changed.split(","):
                path = path.strip()
                if path:
                    entry["recent_files"].add(path)

    prs = await PullRequestRepository(db, org_id=org_id).list_for_bud(bud_id)
    for pr in prs:
        if pr.head_branch in branch_info:
            branch_info[pr.head_branch]["pr"] = {
                "number": pr.github_pr_number,
                "state": pr.state.value if pr.state else None,
                "url": pr.html_url,
            }

    return [
        {
            "branch": entry["branch"],
            "developer": entry.get("developer"),
            "recent_files": sorted(entry["recent_files"])[:20],
            "pr": entry.get("pr"),
        }
        for entry in branch_info.values()
    ]
