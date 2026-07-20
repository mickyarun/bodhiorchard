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

"""Stage G — Persist results (global, runs once per scan).

Wraps ``app.services.scan.phase_impls.persist_results.phase_g_persist``. Updates
``tracked_repositories.head_sha`` + ``last_scanned_at`` for every repo whose
scan came out whole, and writes the ``organizations.config.knowledge``
snapshot. Returns the authoritative active-feature count from the DB.

This phase is global: it runs even when an individual repo's run failed, was
cancelled, or was left mid-flight. Only repos that reached a complete state are
stamped — those two columns mean "this repo was fully scanned at this SHA", and
the skip predicates, the scan-history router and the PR-merge webhook all read
them that way. Stamping a repo whose synthesis (or any other stage) never
finished makes it look complete, so later scans skip the work that never ran and
the repo cannot recover on its own; on a repo whose HEAD never moves again, that
is permanent.

Not the only writer of those columns: ``db_timeline_observer`` stamps a repo on
``on_run_done`` as its run finishes, which is the normal path for a healthy
repo. This phase is the fallback that also covers repos carried through a
Resume, plus the org-config snapshot. A *failed* run never reaches the
observer's stamp, which is exactly why the exclusion here matters.

Called from :mod:`scan_runner._run_global_phases` after the merge
phase. Failures here are loud — without persist, the next scan won't
know which SHAs were already scanned.
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.scan_run import ScanRunRepository
from app.scan.session import with_session
from app.schemas.scan import Community
from app.services.scan.stages import StageContext, StageOutput
from app.services.scan.stages._runtime_context import (
    resolve_runtime_context,
    skipped_runtime_output,
)
from app.services.scan.stages.persist_helpers import collect_head_shas, load_org_config

logger = structlog.get_logger(__name__)


async def _keep_completed_repos(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    scan_id: uuid.UUID,
    new_shas: dict[str, str],
) -> dict[str, str]:
    """Return only the entries of ``new_shas`` whose run completed this scan.

    Keeps proven-complete repos rather than dropping known-failed ones: a
    cancelled scan, or a repo left mid-flight by a dead worker, is not FAILED
    and would otherwise be stamped as fully scanned.
    """
    completed = await ScanRunRepository(db, org_id=org_id).list_completed_repo_paths_for_scan(
        scan_id=scan_id
    )
    kept = {path: sha for path, sha in new_shas.items() if path in completed}
    dropped = sorted(set(new_shas) - completed)
    if dropped:
        # Named individually: a stuck RUNNING looks identical to a clean skip
        # from the outside, and this is the only place it becomes visible.
        logger.info(
            "scan_persist_skipping_incomplete_repos", scan_id=str(scan_id), skipped=dropped
        )
    return kept


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
    missing_shas = max(0, len(repo_paths) - len(new_shas))

    from app.repositories.feature import FeatureRepository
    from app.services.scan.phase_impls.persist_results import phase_g_persist

    try:
        async with with_session(runtime.org_id) as db:
            stamped_shas = await _keep_completed_repos(
                db, org_id=runtime.org_id, scan_id=runtime.scan_id, new_shas=new_shas
            )
            org_config = await load_org_config(db, org_id=runtime.org_id)
            feature_repo = FeatureRepository(db, org_id=runtime.org_id)
            feature_count = await phase_g_persist(
                db=db,
                org_id=runtime.org_id,
                repo_paths=repo_paths,
                new_shas=stamped_shas,
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

    skipped_incomplete = len(new_shas) - len(stamped_shas)
    extras = {
        "persisted": True,
        "feature_count": feature_count,
        "repos_persisted": len(stamped_shas),
        "missing_shas": missing_shas,
        "skipped_incomplete_repos": skipped_incomplete,
        "scan_mode": overall_mode,
        "input_count": len(repo_paths),
        "kept_count": len(stamped_shas),
        "dropped_count": missing_shas + skipped_incomplete,
        "io_label": "repos → persisted",
    }
    logger.info(
        "scan_persist_results_done",
        scan_id=str(runtime.scan_id),
        feature_count=feature_count,
        repos_persisted=len(stamped_shas),
        skipped_incomplete_repos=skipped_incomplete,
        missing_shas=extras["missing_shas"],
    )
    return StageOutput(communities=communities, dropped=[], extras=extras)
