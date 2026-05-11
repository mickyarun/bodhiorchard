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

"""Global (run-once-per-scan) phase orchestration for the pipeline.

After every per-repo workflow has finished, the ``scan_runner``
calls into here to run the cross-repo phases that *can't* be sharded
per-repo: feature merge, skill remap (rebuilds skills with feature
names as modules), persist results, and audit.

Each phase is best-effort: a failure logs and the next phase still
runs. (historical: an earlier pipeline iteration called these same functions
order; we route through the stage registry so each one is uniformly
gated by ``resolve_runtime_context``.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

import structlog

from app.models.scan_phase import ScanPhase
from app.scan.session import with_session
from app.services.scan.stages import StageContext, StageOutput, get_stage

logger = structlog.get_logger(__name__)


# Order matters:
# * ``skill_remap`` rebuilds skill profiles using feature names.
# * ``backend_link`` reads ``backend_route_cache`` rows produced by every
#   per-repo ``extract_routes`` run and writes the cross-layer
#   frontend↔backend ``feature_to_repo`` BACKEND junction rows. Must run
#   AFTER every per-repo workflow (so all backends have extracted) and
#   BEFORE ``persist_results`` (which stamps the org config snapshot).
# * ``persist_results`` writes head_sha + last_scanned_at + the org
#   config snapshot.
# * ``audit`` runs last — it reads from committed checkpoints.
#
# The legacy Claude-driven ``feature_merge`` global phase was removed
# entirely; cross-repo feature dedup is no longer part of the pipeline.
GLOBAL_PHASE_ORDER: tuple[str, ...] = (
    "skill_remap",
    "backend_link",
    "persist_results",
    "audit",
)

# Placeholder repo_name on the global StageContext — phase wrappers
# read ``repo_paths`` for the actual repo set; this string surfaces
# in log lines and is grep-able.
_GLOBAL_REPO_NAME = "global"


async def run_global_phases(
    *,
    org_id: uuid.UUID,
    scan_id: uuid.UUID,
    repo_paths: list[str],
    scan_mode: str = "full",
) -> None:
    """Run every global phase in order; per-phase failures are non-fatal."""
    if not repo_paths:
        return
    counts = await _collect_global_counts(org_id=org_id)
    # Pull the org's Scan-tuning settings (Settings → Code → Scan tuning).
    # Used downstream by stages that respect per-org timeouts; the legacy
    # merge-specific keys (``merge_timeout_seconds`` etc.) remain in the
    # config payload for backwards compatibility but are unused.
    scan_cfg = await _load_scan_cfg(org_id=org_id)
    config: dict[str, Any] = {
        "org_id": str(org_id),
        "scan_id": str(scan_id),
        "repo_paths": repo_paths,
        # Threaded through so persist_results stamps realistic numbers on
        # the org config snapshot.
        "total_features_synthesized": counts["features"],
        "total_profiles": counts["profiles"],
        "unmatched_authors": [],
        "scan_mode": scan_mode,
        "scan_cfg": scan_cfg,
    }
    # The first repo path is just used to satisfy the StageContext;
    # global stages walk the full ``repo_paths`` list internally.
    ctx = StageContext(
        run_id=str(scan_id),
        repo_path=repo_paths[0],
        repo_name=_GLOBAL_REPO_NAME,
    )
    # Stage name → ScanPhase enum so we can write step rows.
    stage_to_phase: dict[str, ScanPhase] = {
        "skill_remap": ScanPhase.SKILL_REMAP,
        "backend_link": ScanPhase.BACKEND_LINK,
        "persist_results": ScanPhase.PERSIST_RESULTS,
        # Audit doesn't have a dedicated phase enum value — log only.
    }
    for stage_name in GLOBAL_PHASE_ORDER:
        phase = stage_to_phase.get(stage_name)
        await _mark_global_phase_running(org_id=org_id, scan_id=scan_id, phase=phase)
        t0 = time.perf_counter()
        try:
            output = await get_stage(stage_name)(ctx, [], config)
        except Exception as exc:
            duration_ms = int((time.perf_counter() - t0) * 1000)
            logger.exception(
                "scan_global_phase_failed",
                scan_id=str(scan_id),
                stage=stage_name,
            )
            await _mark_global_phase_failed(
                org_id=org_id,
                scan_id=scan_id,
                phase=phase,
                error=f"{type(exc).__name__}: {exc}"[:500],
                duration_ms=duration_ms,
            )
            continue
        duration_ms = int((time.perf_counter() - t0) * 1000)
        await _mark_global_phase_done(
            org_id=org_id,
            scan_id=scan_id,
            phase=phase,
            output=output,
            duration_ms=duration_ms,
        )


# --- step-row helpers ---------------------------------------------


async def _all_repo_run_ids(*, org_id: uuid.UUID, scan_id: uuid.UUID) -> list[uuid.UUID]:
    """Return every repo run id for this scan; used to fan global-phase
    step writes across all lanes so the timeline reflects that the
    global phase touched every repo."""
    try:
        async with with_session(org_id) as db:
            from app.repositories.scan_run import ScanRunRepository

            runs = await ScanRunRepository(db, org_id=org_id).find_for_scan(scan_id=scan_id)
            return [r.id for r in runs]
    except Exception:
        logger.exception("scan_global_phase_run_lookup_failed")
        return []


async def _mark_global_phase_running(
    *, org_id: uuid.UUID, scan_id: uuid.UUID, phase: ScanPhase | None
) -> None:
    """Stamp RUNNING on every lane's chip for this global phase."""
    if phase is None:
        return
    run_ids = await _all_repo_run_ids(org_id=org_id, scan_id=scan_id)
    if not run_ids:
        return
    try:
        async with with_session(org_id) as db:
            from app.repositories.scan_step_status import mark_step_running

            for run_id in run_ids:
                await mark_step_running(db, scan_repo_run_id=run_id, phase=phase)
            await db.commit()
    except Exception:
        logger.exception("scan_global_phase_running_write_failed")


async def _mark_global_phase_done(
    *,
    org_id: uuid.UUID,
    scan_id: uuid.UUID,
    phase: ScanPhase | None,
    output: StageOutput,
    duration_ms: int,
) -> None:
    """Stamp DONE + extras on every lane's chip for this global phase."""
    if phase is None:
        return
    run_ids = await _all_repo_run_ids(org_id=org_id, scan_id=scan_id)
    if not run_ids:
        return
    try:
        async with with_session(org_id) as db:
            from app.repositories.scan_step_status import mark_step_done

            extras = dict(output.extras)
            input_count = _extract_count(extras, "input_count", 0)
            kept_count = _extract_count(extras, "kept_count", len(output.communities))
            dropped_count = _extract_count(extras, "dropped_count", len(output.dropped))
            for run_id in run_ids:
                await mark_step_done(
                    db,
                    scan_repo_run_id=run_id,
                    phase=phase,
                    duration_ms=duration_ms,
                    input_count=input_count,
                    kept_count=kept_count,
                    dropped_count=dropped_count,
                    extras=extras,
                )
            await db.commit()
    except Exception:
        logger.exception("scan_global_phase_done_write_failed")


def _extract_count(extras: dict[str, Any], key: str, default: int) -> int:
    """Read an int count override from extras; fall back to ``default``.

    Mirrors ``workflow._extras_count`` for the global-phase recording
    path. Global stages put their counts in extras (since they don't
    use ``StageOutput.communities`` as the real output) so the chip
    can show e.g. "31 features → 4 canonical features".
    """
    value = extras.get(key)
    return int(value) if isinstance(value, int) else default


async def _mark_global_phase_failed(
    *,
    org_id: uuid.UUID,
    scan_id: uuid.UUID,
    phase: ScanPhase | None,
    error: str,
    duration_ms: int,
) -> None:
    """Stamp FAILED + error message on every lane's chip for this global phase."""
    if phase is None:
        return
    run_ids = await _all_repo_run_ids(org_id=org_id, scan_id=scan_id)
    if not run_ids:
        return
    try:
        async with with_session(org_id) as db:
            from app.repositories.scan_step_status import mark_step_failed

            for run_id in run_ids:
                await mark_step_failed(
                    db,
                    scan_repo_run_id=run_id,
                    phase=phase,
                    error=error,
                    duration_ms=duration_ms,
                )
            await db.commit()
    except Exception:
        logger.exception("scan_global_phase_failed_write_failed")


async def _load_scan_cfg(*, org_id: uuid.UUID) -> dict[str, int]:
    """Read the Scan-tuning section of the org config for global phases.

    Mirror of ``scan_runner._load_scan_cfg`` — kept here as a separate
    helper because ``run_global_phases`` is invoked outside the
    per-repo fanout that already loaded scan_cfg into ``runtime_overrides``.
    The legacy ``merge_timeout_seconds`` key is preserved in the return
    value for backwards compatibility with consumers that still read it.
    """
    from app.repositories.organization import OrganizationRepository

    try:
        async with with_session(org_id) as db:
            org = await OrganizationRepository(db).get_by_id(org_id)
            cfg = dict((org.config or {}).get("scan", {})) if org else {}
    except Exception:
        logger.exception("scan_global_load_scan_cfg_failed", org_id=str(org_id))
        cfg = {}
    return {
        "timeout_seconds": int(cfg.get("timeout_seconds") or 300),
        "merge_timeout_seconds": int(cfg.get("merge_timeout_seconds") or 300),
        "max_turns": int(cfg.get("max_turns") or 40),
    }


async def _collect_global_counts(*, org_id: uuid.UUID) -> dict[str, int]:
    """Snapshot the current active-feature + skill-profile counts.

    Threaded into ``config["total_features_synthesized"]`` /
    ``["total_profiles"]`` so ``persist_results`` stamps realistic
    numbers on the org config snapshot instead of zeros.
    """
    from app.repositories.feature import FeatureRepository
    from app.repositories.skill_profile import SkillProfileRepository

    try:
        async with with_session(org_id) as db:
            features = await FeatureRepository(db, org_id=org_id).count_active_for_org()
            profiles = await SkillProfileRepository(db, org_id=org_id).count_profiles()
    except Exception:
        logger.exception("scan_global_counts_failed", org_id=str(org_id))
        return {"features": 0, "profiles": 0}
    return {"features": features, "profiles": profiles}
