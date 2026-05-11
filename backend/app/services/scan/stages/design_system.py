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

"""Stage E1b — Design system extract (per-repo, async fire-and-forget).

Thin wrapper around ``app.services.scan_design_system.maybe_extract_design_system``.
Discovers UI source files in the worktree, computes their hash, and
enqueues a background job to extract design tokens. The legacy function
is fire-and-forget — failures don't block the rest of the pipeline.

Sandbox runs (no context) no-op.
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog

from app.models.tracked_repository import TrackedRepository
from app.scan.session import with_session
from app.schemas.scan import Community
from app.services.scan.stages import StageContext, StageOutput
from app.services.scan.stages._runtime_context import (
    resolve_runtime_context,
    skipped_runtime_output,
)
from app.services.scan.stages._skip import stage_output_for_skip
from app.services.scan.stages._skip_predicates import should_skip_design_system

logger = structlog.get_logger(__name__)


async def run(
    ctx: StageContext,
    communities: list[Community],
    config: dict[str, Any],
) -> StageOutput:
    """Enqueue design-system extraction for this repo if applicable."""
    runtime = resolve_runtime_context(config)
    if runtime is None:
        return StageOutput(communities=communities, dropped=[], extras=skipped_runtime_output())

    repo_id_raw = config.get("repo_id")
    if not repo_id_raw:
        return StageOutput(
            communities=communities,
            dropped=[],
            extras={
                "reason": "repo_id_missing",
                "skipped_reason": "repo_id not threaded into stage config",
                "io_label": "repo → design tokens",
            },
        )
    repo_id = repo_id_raw if isinstance(repo_id_raw, uuid.UUID) else uuid.UUID(str(repo_id_raw))

    full_rescan = bool(config.get("full_rescan", False))

    async with with_session(runtime.org_id) as db:
        decision = await should_skip_design_system(
            db,
            org_id=runtime.org_id,
            repo_id=repo_id,
            repo_path=ctx.repo_path,
            full_rescan=full_rescan,
        )
    if decision.skip:
        extras = stage_output_for_skip(decision, io_label="repo → design tokens").extras
        return StageOutput(communities=communities, dropped=[], extras=extras)

    try:
        async with with_session(runtime.org_id) as db:
            from app.services.scan_design_system import maybe_extract_design_system

            tracked_repo = await db.get(TrackedRepository, repo_id)
            await maybe_extract_design_system(
                db=db,
                org_id=runtime.org_id,
                scan_path=ctx.repo_path,
                tracked_repo=tracked_repo,
                full_rescan=full_rescan,
            )
            await db.commit()
    except Exception as exc:
        # Design-system extract is fire-and-forget. Log and continue.
        logger.warning(
            "scan_design_system_failed",
            repo=ctx.repo_name,
            error=str(exc)[:300],
        )
        return StageOutput(
            communities=communities,
            dropped=[],
            extras={
                "queued": False,
                "error": str(exc)[:300],
                "io_label": "repo → design tokens",
                "skipped_reason": f"extraction error: {str(exc)[:120]}",
            },
        )

    logger.info("scan_design_system_queued", repo=ctx.repo_name)
    return StageOutput(
        communities=communities,
        dropped=[],
        extras={
            "queued": True,
            "io_label": "repo → design tokens",
            # Fire-and-forget: the actual extraction runs out-of-band, so
            # the chip reads "queued" rather than a real produced count.
            "skipped_reason": "queued — extraction runs in the background",
        },
    )
