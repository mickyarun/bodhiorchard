# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Stage E — Skill extraction (per-repo).

Wraps the legacy ``app.services.scan.phase_impls.skill_extraction.phase_e_skills``
in the v2 stage signature without touching the original. Runs git-log
analysis against the worktree, optionally auto-creates members, and
upserts ``skill_profiles`` rows.

Only fires inside a real v2 scan (org_id + scan_id supplied via config);
sandbox runs no-op.
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog

from app.scan.session import with_session
from app.schemas.scan import Community
from app.services.scan.stages import StageContext, StageOutput
from app.services.scan.stages._skip import stage_output_for_skip
from app.services.scan.stages._skip_predicates import should_skip_skill_extraction
from app.services.scan.stages._v2_context import resolve_v2_context, skipped_v2_output

logger = structlog.get_logger(__name__)

# How many unmatched author emails to surface in the stage extras. The
# UI uses this to render a "couldn't match" hint without blowing up the
# JSON payload when a repo has hundreds of orphan authors.
_UNMATCHED_EMAIL_EXTRA_CAP = 20


async def run(
    ctx: StageContext,
    communities: list[Community],
    config: dict[str, Any],
) -> StageOutput:
    """Run git-log skill extraction; pass ``communities`` through unchanged."""
    v2 = resolve_v2_context(config)
    if v2 is None:
        return StageOutput(communities=communities, dropped=[], extras=skipped_v2_output())

    repo_id_raw = config.get("v2_repo_id")
    if repo_id_raw is not None:
        repo_id = uuid.UUID(str(repo_id_raw))
        async with with_session(v2.org_id) as db:
            decision = await should_skip_skill_extraction(
                db,
                org_id=v2.org_id,
                repo_id=repo_id,
                repo_path=ctx.repo_path,
                full_rescan=bool(config.get("v2_full_rescan", False)),
            )
        if decision.skip:
            extras = stage_output_for_skip(
                decision, io_label="git authors → skill profiles"
            ).extras
            return StageOutput(communities=communities, dropped=[], extras=extras)

    from app.repositories.user import UserRepository
    from app.services.git_analyzer import analyze_repo_skills
    from app.services.scan.phase_impls.skill_extraction import phase_e_skills

    skill_entries = await analyze_repo_skills(ctx.repo_path)
    if not skill_entries:
        logger.info(
            "scan_skill_extraction_no_entries",
            repo=ctx.repo_name,
        )
        return StageOutput(
            communities=communities,
            dropped=[],
            extras={
                "profiles_added": 0,
                "unmatched_count": 0,
                "input_count": 0,
                "kept_count": 0,
                "io_label": "git authors → skill profiles",
                "skipped_reason": "no git-log activity",
            },
        )

    async with with_session(v2.org_id) as db:
        email_to_user = await UserRepository(db).get_email_map(v2.org_id)
        scan_cfg = config.get("scan_cfg", {}) or {}
        profiles_added, unmatched = await phase_e_skills(
            db=db,
            org_id=v2.org_id,
            repo_path=ctx.repo_path,
            skill_entries=skill_entries,
            email_to_user=email_to_user,
            scan_cfg=scan_cfg,
        )
        await db.commit()

    extras = {
        "profiles_added": profiles_added,
        "unmatched_count": len(unmatched),
        "unmatched_emails": unmatched[:_UNMATCHED_EMAIL_EXTRA_CAP],
        # input = unique authors mined from git log (matched + unmatched);
        # kept  = profiles upserted into ``skill_profiles``.
        "input_count": len(skill_entries),
        "kept_count": profiles_added,
        "dropped_count": len(unmatched),
        "io_label": "git authors → skill profiles",
    }
    logger.info(
        "scan_skill_extraction_done",
        repo=ctx.repo_name,
        profiles_added=profiles_added,
        unmatched_count=len(unmatched),
    )
    return StageOutput(communities=communities, dropped=[], extras=extras)
