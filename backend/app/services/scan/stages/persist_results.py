# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Stage G — Persist results (global, runs once per scan).

Wraps ``app.services.scan.phase_impls.persist_results.phase_g_persist``. Updates
``tracked_repositories.head_sha`` + ``last_scanned_at`` for every
scanned repo and writes the ``organizations.config.knowledge``
snapshot. Returns the authoritative active-feature count from the DB.

Called from :mod:`scan_runner._run_global_phases` after the merge
phase. Failures here are loud — without persist, the next scan won't
know which SHAs were already scanned.
"""

from __future__ import annotations

from typing import Any

import structlog

from app.scan.session import with_session
from app.schemas.scan import Community
from app.services.scan.stages import StageContext, StageOutput
from app.services.scan.stages._runtime_context import (
    resolve_runtime_context,
    skipped_runtime_output,
)
from app.services.scan.stages.persist_helpers import collect_head_shas, load_org_config

logger = structlog.get_logger(__name__)


async def run(
    ctx: StageContext,
    communities: list[Community],
    config: dict[str, Any],
) -> StageOutput:
    """Stamp tracked_repositories + org config after the scan succeeds."""
    runtime = resolve_runtime_context(config)
    if runtime is None:
        return StageOutput(communities=communities, dropped=[], extras=skipped_runtime_output())

    repo_paths_raw = config.get("repo_paths") or [ctx.repo_path]
    repo_paths = list(repo_paths_raw) if isinstance(repo_paths_raw, list) else [ctx.repo_path]
    overall_mode = str(config.get("scan_mode", "full"))
    total_profiles = int(config.get("total_profiles", 0))
    unmatched_raw = config.get("unmatched_authors") or []
    all_unmatched = list(unmatched_raw) if isinstance(unmatched_raw, list) else []

    new_shas = await collect_head_shas(repo_paths)

    from app.repositories.feature import FeatureRepository
    from app.services.scan.phase_impls.persist_results import phase_g_persist

    try:
        async with with_session(runtime.org_id) as db:
            org_config = await load_org_config(db, org_id=runtime.org_id)
            feature_repo = FeatureRepository(db, org_id=runtime.org_id)
            feature_count = await phase_g_persist(
                db=db,
                org_id=runtime.org_id,
                repo_paths=repo_paths,
                new_shas=new_shas,
                config=org_config,
                total_profiles=total_profiles,
                all_unmatched=all_unmatched,
                overall_mode=overall_mode,
                feature_repo=feature_repo,
            )
            # phase_g_persist commits internally; no second commit here.
    except Exception as exc:
        logger.exception(
            "scan_persist_results_failed",
            scan_id=str(runtime.scan_id),
            repo_count=len(repo_paths),
        )
        return StageOutput(
            communities=communities,
            dropped=[],
            extras={
                "persisted": False,
                "error": str(exc)[:300],
                "input_count": len(repo_paths),
                "kept_count": 0,
                "dropped_count": len(repo_paths),
                "io_label": "repos → persisted",
            },
        )

    missing_shas = max(0, len(repo_paths) - len(new_shas))
    extras = {
        "persisted": True,
        "feature_count": feature_count,
        "repos_persisted": len(new_shas),
        "missing_shas": missing_shas,
        "scan_mode": overall_mode,
        "input_count": len(repo_paths),
        "kept_count": len(new_shas),
        "dropped_count": missing_shas,
        "io_label": "repos → persisted",
    }
    logger.info(
        "scan_persist_results_done",
        scan_id=str(runtime.scan_id),
        feature_count=feature_count,
        repos_persisted=len(new_shas),
        missing_shas=extras["missing_shas"],
    )
    return StageOutput(communities=communities, dropped=[], extras=extras)
