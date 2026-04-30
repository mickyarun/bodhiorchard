# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Stage E2 — Skill remap (global, runs once per scan).

Wraps ``app.services.scan.phase_impls.skill_remap.phase_e2_skill_remap`` in the v2
stage signature. Re-runs git-log analysis with the freshly-synthesised
feature map so skills attach to feature names rather than directories.

Honours the legacy 70% coverage threshold inside ``phase_e2_skill_remap``
— full wipe + replace only when new analysis covers ≥ 70% of the old
profile count, otherwise partial update.

Skipped from any per-repo pipeline; the v2 scan_runner schedules this
once after every per-repo run completes (Phase 9 work — for now this
stage runs in-place when the workflow lists it).
"""

from __future__ import annotations

from typing import Any

import structlog

from app.scan.session import with_session
from app.schemas.scan import Community
from app.services.scan.stages import StageContext, StageOutput
from app.services.scan.stages._v2_context import resolve_v2_context, skipped_v2_output

logger = structlog.get_logger(__name__)


async def run(
    ctx: StageContext,
    communities: list[Community],
    config: dict[str, Any],
) -> StageOutput:
    """Re-derive skill profiles using feature names as modules."""
    v2 = resolve_v2_context(config)
    if v2 is None:
        return StageOutput(communities=communities, dropped=[], extras=skipped_v2_output())

    repo_paths_raw = config.get("v2_repo_paths")
    if isinstance(repo_paths_raw, list) and repo_paths_raw:
        repo_paths = list(repo_paths_raw)
    else:
        # Misconfiguration safety net: skill_remap is meant to be invoked
        # once per scan with the union of repo paths. When called via the
        # per-repo workflow without ``v2_repo_paths`` we fall back to the
        # current repo to avoid crashing, but log loudly so the operator
        # knows skills are being clobbered N times instead of once.
        logger.warning(
            "scan_skill_remap_single_repo_fallback",
            scan_id=str(v2.scan_id),
            repo=ctx.repo_name,
        )
        repo_paths = [ctx.repo_path]

    from app.repositories.user import UserRepository
    from app.services.scan.phase_impls.skill_remap import phase_e2_skill_remap

    async with with_session(v2.org_id) as db:
        email_to_user = await UserRepository(db).get_email_map(v2.org_id)
        profiles = await phase_e2_skill_remap(
            db=db,
            org_id=v2.org_id,
            repo_paths=list(repo_paths),
            email_to_user=email_to_user,
            scan_id=str(v2.scan_id),
        )
        await db.commit()

    logger.info(
        "scan_skill_remap_done",
        scan_id=str(v2.scan_id),
        profiles=profiles,
    )
    return StageOutput(
        communities=communities,
        dropped=[],
        extras={
            "profiles": profiles,
            # ``profiles`` is the post-remap row count returned by the
            # legacy phase. Without a pre-remap snapshot we don't have
            # a meaningful input number — leave it equal so the chip
            # reads "N → N" rather than "0 → N".
            "input_count": profiles,
            "kept_count": profiles,
            "io_label": "skill profiles → remapped",
        },
    )
