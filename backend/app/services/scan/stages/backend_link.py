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

"""Stage wrapper for the global ``backend_link`` phase.

Mirrors :mod:`stages.skill_remap`'s shape. The orchestration logic
lives in :mod:`phase_impls.backend_link`; this wrapper just adapts its
counters into the ``StageOutput`` contract the workflow expects.

Runs once per scan after every per-repo workflow finishes, scheduled
via :data:`global_phases.GLOBAL_PHASE_ORDER`. There's no per-repo
``backend_link`` stage — the per-repo half is now :mod:`extract_routes`,
which writes the ``backend_route_cache`` rows this phase reads.
"""

from __future__ import annotations

from typing import Any

import structlog

from app.scan.session import with_session
from app.schemas.scan import Community
from app.services.scan.phase_impls.backend_link import run_backend_link
from app.services.scan.stages import StageContext, StageOutput
from app.services.scan.stages._runtime_context import (
    resolve_runtime_context,
    skipped_runtime_output,
)
from app.services.scan.stages._skip import stage_output_for_skip
from app.services.scan.stages._skip_predicates import should_skip_backend_link

logger = structlog.get_logger(__name__)


async def run(
    ctx: StageContext,
    communities: list[Community],
    config: dict[str, Any],
) -> StageOutput:
    """Run the cross-layer linker and surface counters on ``extras``."""
    runtime = resolve_runtime_context(config)
    if runtime is None:
        return StageOutput(communities=communities, dropped=[], extras=skipped_runtime_output())

    # Skip when no per-repo input changed this scan. The linker's output
    # is a pure function of the route cache + frontend feature sets, so
    # if nothing wrote to either since the last linker run, re-emitting
    # the same junction rows is wasted I/O.
    async with with_session(runtime.org_id) as db:
        decision = await should_skip_backend_link(
            db, org_id=runtime.org_id, scan_id=runtime.scan_id
        )
    if decision.skip:
        return stage_output_for_skip(decision, io_label="features → backend-linked")

    counters = await run_backend_link(org_id=runtime.org_id, scan_id=runtime.scan_id)
    extras: dict[str, Any] = {
        **counters,
        "input_count": counters["features_processed"],
        "kept_count": counters["features_linked"],
        "io_label": "features → backend-linked",
    }
    return StageOutput(communities=communities, dropped=[], extras=extras)
