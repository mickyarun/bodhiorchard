# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

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

from app.schemas.scan import Community
from app.services.scan.phase_impls.backend_link import run_backend_link
from app.services.scan.stages import StageContext, StageOutput
from app.services.scan.stages._v2_context import resolve_v2_context, skipped_v2_output

logger = structlog.get_logger(__name__)


async def run(
    ctx: StageContext,
    communities: list[Community],
    config: dict[str, Any],
) -> StageOutput:
    """Run the cross-layer linker and surface counters on ``extras``."""
    v2 = resolve_v2_context(config)
    if v2 is None:
        return StageOutput(communities=communities, dropped=[], extras=skipped_v2_output())

    counters = await run_backend_link(org_id=v2.org_id, scan_id=v2.scan_id)
    extras: dict[str, Any] = {
        **counters,
        "input_count": counters["features_processed"],
        "kept_count": counters["features_linked"],
        "io_label": "features → backend-linked",
    }
    return StageOutput(communities=communities, dropped=[], extras=extras)
