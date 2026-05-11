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

"""Stage B1 — Repo setup (per-repo).

Wraps the legacy ``app.services.scan.phase_impls.repo_setup.phase_b1_repo_setup`` in
the stage signature. Owns the worktree bootstrap, MCP / git-hooks
install, ``.bodhiorchard/init-setup`` branch push, and the GitHub-App
backed PR-open (or compare-URL fallback when the App is not connected).

Runs as the **first** per-repo stage so the worktrees and hooks are in
place before code analysis touches the repo, and so the row's setup-PR
chip flips out of "Setup pending" as early as possible.

Communities are passed through unchanged — repo_setup is a side-effect
stage that only reports counts in ``extras`` for the timeline popover.
Sandbox runs (no org/scan context) no-op.
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog

from app.scan.session import with_session
from app.schemas.scan import Community
from app.services.scan.stages import StageContext, StageOutput
from app.services.scan.stages._runtime_context import (
    resolve_runtime_context,
    skipped_runtime_output,
)
from app.services.scan.stages._skip import stage_output_for_skip
from app.services.scan.stages._skip_predicates import should_skip_repo_setup

logger = structlog.get_logger(__name__)


async def run(
    ctx: StageContext,
    communities: list[Community],
    config: dict[str, Any],
) -> StageOutput:
    """Drive the per-repo setup phase, then pass communities through."""
    runtime = resolve_runtime_context(config)
    repo_id_raw = config.get("repo_id")
    if runtime is None or repo_id_raw is None:
        return StageOutput(communities=communities, dropped=[], extras=skipped_runtime_output())

    repo_id = uuid.UUID(str(repo_id_raw))

    # Setup is one-time and SHA-independent — honored even on full_rescan.
    async with with_session(runtime.org_id) as db:
        decision = await should_skip_repo_setup(db, org_id=runtime.org_id, repo_id=repo_id)
    if decision.skip:
        skipped_extras = stage_output_for_skip(decision, io_label="repo → MCP setup PR").extras
        return StageOutput(communities=communities, dropped=[], extras=skipped_extras)

    from app.repositories.tracked_repository import TrackedRepoRepository
    from app.services.scan.phase_impls.repo_setup import phase_b1_repo_setup

    async with with_session(runtime.org_id) as db:
        tracked_repo = await TrackedRepoRepository(db, org_id=runtime.org_id).get_by_id(repo_id)
        # ``phase_b1_repo_setup`` writes ``setup_branch_pushed_at`` and
        # the ``setup_pr_*`` columns directly onto ``tracked_repo``;
        # commit so the row chip on /settings/code reflects the new
        # state on the next list_repos request.
        pr_msg = await phase_b1_repo_setup(
            db=db,
            org_id=runtime.org_id,
            repo_path=ctx.repo_path,
            repo_name=ctx.repo_name,
            tracked_repo=tracked_repo,
            scan_id=str(runtime.scan_id),
            base_pct=0,
        )
        await db.commit()

        # Re-read so we can surface the persisted state to the timeline
        # popover without holding the session open longer than needed.
        refreshed = await TrackedRepoRepository(db, org_id=runtime.org_id).get_by_id(repo_id)

    setup_pr_state = (
        refreshed.setup_pr_state.value
        if refreshed and refreshed.setup_pr_state is not None
        else None
    )
    branch_pushed = bool(refreshed and refreshed.setup_branch_pushed_at)

    extras: dict[str, Any] = {
        "branch_pushed": branch_pushed,
        "setup_pr_state": setup_pr_state,
        "setup_pr_url": refreshed.setup_pr_url if refreshed else None,
        "manual_message": pr_msg,
        # Counts feed the timeline chip (the popover renders these as the
        # input → kept → dropped triple). repo_setup operates on one
        # repo so the natural mapping is 1 → 1 → 0.
        "input_count": 1,
        "kept_count": 1,
        "dropped_count": 0,
        "io_label": "repo → MCP setup PR",
    }
    logger.info(
        "scan_repo_setup_done",
        repo=ctx.repo_name,
        branch_pushed=branch_pushed,
        setup_pr_state=setup_pr_state,
    )
    return StageOutput(communities=communities, dropped=[], extras=extras)
