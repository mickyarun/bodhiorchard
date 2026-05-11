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

"""Per-stage skip predicates for the per-repo scan pipeline.

Each predicate answers a single question: "is this stage's output already
current for the repo's HEAD commit?" — and is the only place in the codebase
that knows the answer for that stage. Stages call their predicate at the top
of ``run`` and short-circuit through ``_skip.stage_output_for_skip`` when it
returns ``skip=True``.

Two skip categories:

* **Always-honored** — ``should_skip_repo_setup`` and ``should_skip_indexing``
  ignore ``full_rescan``. Re-running them on the same SHA produces identical
  output for nontrivial cost (the indexer is SHA-keyed; setup is one-time).
* **Bypassable** — ``should_skip_skill_extraction``,
  ``should_skip_design_system``, ``should_skip_feature_synthesis`` accept a
  ``full_rescan`` flag and return ``skip=False`` when it's True so Reset /
  Full Rescan flows can rebuild downstream artifacts deterministically.

The asymmetric signatures are deliberate: the always-honored predicates do
not take ``full_rescan`` so reviewers cannot wire ``True`` through to them.

Every predicate is fail-safe to ``skip=False``: an unexpected exception
returns ``SkipDecision(skip=False, reason="predicate_error: <name>")`` and
logs ``scan_skip_predicate_error``. We never silently turn a bug in
skip detection into a skipped scan.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scan_phase import ScanPhase
from app.models.scan_run_enums import StepStatus
from app.repositories.cluster_cache import ClusterCacheRepository
from app.repositories.design_system import DesignSystemRefRepository
from app.repositories.feature import FeatureRepository
from app.repositories.scan_step_status import (
    find_latest_step_status_for_repo_phase,
    has_done_step_for_scan,
)
from app.repositories.tracked_repository import TrackedRepoRepository
from app.services.git_analyzer import get_head_sha

logger = structlog.get_logger(__name__)


@dataclass(slots=True, frozen=True)
class SkipDecision:
    """Result of a per-stage skip check.

    ``head_sha`` is included on positive decisions so the chip popover can
    render "head_sha unchanged: 2e570405" without the stage having to fetch
    the SHA twice.
    """

    skip: bool
    reason: str | None = None
    head_sha: str | None = None


# --- Always-honored predicates ---------------------------------------------


async def should_skip_repo_setup(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    repo_id: uuid.UUID,
) -> SkipDecision:
    """Skip when the setup branch was pushed AND the setup PR is recorded.

    No SHA dependency — the setup branch is one-time and stays valid across
    commits. Re-pushing on every scan churns the GitHub App for no value.
    """
    try:
        tracked = await TrackedRepoRepository(db, org_id=org_id).get_by_id(repo_id)
        if tracked is None:
            return SkipDecision(skip=False)
        if tracked.setup_branch_pushed_at is None or tracked.setup_pr_url is None:
            return SkipDecision(skip=False)
        return SkipDecision(
            skip=True,
            reason=f"setup PR already open: {tracked.setup_pr_url}",
        )
    except Exception:
        logger.exception("scan_skip_predicate_error", stage="repo_setup")
        return SkipDecision(skip=False, reason="predicate_error: repo_setup")


async def should_skip_indexing(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    repo_id: uuid.UUID,
    head_sha: str,
    force_reindex: bool = False,
) -> SkipDecision:
    """Skip when ``cluster_cache`` already has rows for ``(repo_id, head_sha)``.

    The code indexer's output is fully captured in two cache tables —
    ``cluster_cache`` (one row per cluster) and ``repo_graph_cache`` (one
    row per repo). If cluster_cache rows exist for the current SHA we
    have everything Stage 1 (extract) will need, so skipping the indexer
    saves ~10–60s per repo on resume.
    """
    if force_reindex:
        return SkipDecision(skip=False, reason="force_reindex set")
    if not head_sha:
        return SkipDecision(skip=False, reason="no head_sha")
    try:
        repo = ClusterCacheRepository(db, org_id=org_id)
        rows = await repo.list_for_repo_sha(repo_id=repo_id, head_sha=head_sha)
        if not rows:
            return SkipDecision(skip=False, reason="cluster_cache empty for SHA")
        return SkipDecision(
            skip=True,
            reason=f"head_sha unchanged: {head_sha[:8]}",
            head_sha=head_sha,
        )
    except Exception:
        logger.exception("scan_skip_predicate_error", stage="indexing")
        return SkipDecision(skip=False, reason="predicate_error: indexing")


# --- Bypassable predicates -------------------------------------------------


async def _bypass_if_prior_step_failed(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    repo_id: uuid.UUID,
    phase: ScanPhase,
) -> SkipDecision | None:
    """Return a no-skip decision when the most recent step for (repo, phase) is FAILED.

    Returns None when the prior attempt succeeded, was skipped, or has no
    record — meaning the predicate's normal cache logic applies. Lets each
    call site collapse to a single ``if (d := await ...) is not None: return d``
    instead of duplicating a status comparison + reason string per phase.
    """
    status = await find_latest_step_status_for_repo_phase(
        db, org_id=org_id, repo_id=repo_id, phase=phase
    )
    if status != StepStatus.FAILED:
        return None
    return SkipDecision(skip=False, reason=f"prior {phase.value} step failed")


async def should_skip_skill_extraction(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    repo_id: uuid.UUID,
    repo_path: str,
    full_rescan: bool,
) -> SkipDecision:
    """Skip when tracked.head_sha == HEAD AND not full_rescan.

    skill_profiles are org-scoped per (user, module) — they don't carry a
    repo_id, so the existence proxy is "this repo was successfully scanned
    before". ``tracked.head_sha`` is stamped only by the global persist
    phase after a complete scan, which makes it the right marker.
    """
    if full_rescan:
        return SkipDecision(skip=False, reason="full_rescan set")
    try:
        match, head = await _head_sha_matches_tracked(
            db, org_id=org_id, repo_id=repo_id, repo_path=repo_path
        )
        if not match or head is None:
            return SkipDecision(skip=False)
        bypass = await _bypass_if_prior_step_failed(
            db, org_id=org_id, repo_id=repo_id, phase=ScanPhase.SKILL_EXTRACTION
        )
        if bypass is not None:
            return bypass
        return SkipDecision(
            skip=True,
            reason=f"head_sha unchanged: {head[:8]}",
            head_sha=head,
        )
    except Exception:
        logger.exception("scan_skip_predicate_error", stage="skill_extraction")
        return SkipDecision(skip=False, reason="predicate_error: skill_extraction")


async def should_skip_design_system(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    repo_id: uuid.UUID,
    repo_path: str,
    full_rescan: bool,
) -> SkipDecision:
    """Skip when a design_system row exists for the repo AND tracked.head_sha == HEAD."""
    if full_rescan:
        return SkipDecision(skip=False, reason="full_rescan set")
    try:
        match, head = await _head_sha_matches_tracked(
            db, org_id=org_id, repo_id=repo_id, repo_path=repo_path
        )
        if not match or head is None:
            return SkipDecision(skip=False)
        if not await DesignSystemRefRepository(db, org_id=org_id).exists_by_repo_id(repo_id):
            return SkipDecision(skip=False, reason="no prior design system extracted")
        bypass = await _bypass_if_prior_step_failed(
            db, org_id=org_id, repo_id=repo_id, phase=ScanPhase.DESIGN_SYSTEM_EXTRACT
        )
        if bypass is not None:
            return bypass
        return SkipDecision(
            skip=True,
            reason=f"design system already extracted at {head[:8]}",
            head_sha=head,
        )
    except Exception:
        logger.exception("scan_skip_predicate_error", stage="design_system")
        return SkipDecision(skip=False, reason="predicate_error: design_system")


async def should_skip_feature_synthesis(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    repo_id: uuid.UUID,
    repo_path: str,
    full_rescan: bool,
) -> SkipDecision:
    """Skip when ≥1 current ``features`` row exists for the repo
    AND ``tracked.head_sha == HEAD``.

    B2 is the writer of ``features`` (staging-only). The right cache
    marker for "B2 already produced output for this SHA" is a current
    feature row whose PRIMARY junction points at this
    repo — wiping KIs must NOT force B2 to re-synthesise unchanged repos.
    """
    if full_rescan:
        return SkipDecision(skip=False, reason="full_rescan set")
    try:
        match, head = await _head_sha_matches_tracked(
            db, org_id=org_id, repo_id=repo_id, repo_path=repo_path
        )
        if not match or head is None:
            return SkipDecision(skip=False)
        synth_repo = FeatureRepository(db, org_id=org_id)
        per_repo_counts = await synth_repo.count_active_per_repo()
        synth_count = per_repo_counts.get(repo_id, 0)
        if synth_count == 0:
            return SkipDecision(skip=False, reason="no prior synth rows for repo")
        bypass = await _bypass_if_prior_step_failed(
            db, org_id=org_id, repo_id=repo_id, phase=ScanPhase.FEATURE_SYNTHESIS
        )
        if bypass is not None:
            return bypass
        return SkipDecision(
            skip=True,
            reason=f"{synth_count} synth rows already staged at {head[:8]}",
            head_sha=head,
        )
    except Exception:
        logger.exception("scan_skip_predicate_error", stage="feature_synthesis")
        return SkipDecision(skip=False, reason="predicate_error: feature_synthesis")


# --- Global-phase predicates ------------------------------------------------


async def should_skip_backend_link(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    scan_id: uuid.UUID,
) -> SkipDecision:
    """Skip the global ``backend_link`` phase when no input changed this scan.

    The linker reads two inputs:

    * Every backend repo's ``backend_route_cache`` rows (written by
      ``EXTRACT_ROUTES``).
    * Every frontend repo's feature set + PRIMARY ``code_locations``
      (written by ``FEATURE_SYNTHESIS``).

    If neither phase reached ``DONE`` for ANY repo in this scan — i.e.
    every per-repo step row is ``SKIPPED_CACHE``, ``QUEUED``, or absent —
    then the linker would re-emit byte-identical output. Skip and return
    the cached counters via ``stage_output_for_skip``.

    Fail-safe: any DB error returns ``skip=False``. Doing nothing is the
    correct fall-back because the linker is idempotent — re-running it
    when nothing changed is wasteful but never incorrect.
    """
    try:
        any_input_changed = await has_done_step_for_scan(
            db,
            org_id=org_id,
            scan_id=scan_id,
            phases=[ScanPhase.FEATURE_SYNTHESIS, ScanPhase.EXTRACT_ROUTES],
        )
        if any_input_changed:
            return SkipDecision(
                skip=False,
                reason="at least one FEATURE_SYNTHESIS or EXTRACT_ROUTES step DONE",
            )
        return SkipDecision(
            skip=True,
            reason=(
                "no per-repo FEATURE_SYNTHESIS or EXTRACT_ROUTES step "
                "reached DONE this scan — linker inputs unchanged"
            ),
        )
    except Exception:
        logger.exception("scan_skip_predicate_error", stage="backend_link")
        return SkipDecision(skip=False, reason="predicate_error: backend_link")


# --- Shared building blocks ------------------------------------------------


async def _head_sha_matches_tracked(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    repo_id: uuid.UUID,
    repo_path: str,
) -> tuple[bool, str | None]:
    """Return (matches, head_sha). ``head_sha`` is the matching SHA on True; None otherwise.

    Returns ``(False, None)`` when:

    * the tracked row is missing or has empty head_sha (first scan);
    * git rev-parse fails (corrupt worktree, missing git);
    * the worktree HEAD doesn't equal tracked.head_sha.
    """
    tracked = await TrackedRepoRepository(db, org_id=org_id).get_by_id(repo_id)
    if tracked is None or not tracked.head_sha:
        return False, None
    current = await get_head_sha(repo_path)
    if current is None or current != tracked.head_sha:
        return False, None
    return True, current


__all__ = [
    "SkipDecision",
    "should_skip_backend_link",
    "should_skip_design_system",
    "should_skip_feature_synthesis",
    "should_skip_indexing",
    "should_skip_repo_setup",
    "should_skip_skill_extraction",
]
