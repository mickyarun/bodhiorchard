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

"""PR-merge narrow synthesis.

Called inline from :mod:`app.services.scan.pr_merge_update` when a PR
touches a small number of clusters. Runs Claude over the affected
clusters only — handing it each cluster's currently-known feature so
it can update / insert / soft-delete (via the reconciler) against the
merge head SHA.

Concretely, :func:`run_narrow_synthesis`:

1. Reads the affected clusters' rows from ``cluster_cache`` at
   ``head_sha`` and builds ``Community`` payloads.
2. Looks up the currently-known feature for each cluster signature
   (active + inactive) so the prompt can include update context.
3. Builds the narrow synthesis prompt (see
   :mod:`app.services.scan.synthesis.narrow_prompt`).
4. Runs Claude through the existing ``ClaudeCodeEngine`` against an
   internally-minted MCP token.
5. Drains the synthesis accumulator and calls
   ``reconcile_features_for_repo`` with a ``candidate_filter`` scoped
   to the affected signature set, passing the merge ``head_sha`` so
   the reconciler stamps ``deactivated_at_sha`` on any soft-deletes.

The narrow path **never** triggers a full scan. The over-cap fall-back
that does that lives in the dispatcher
(:mod:`app.services.scan.pr_merge_update`).

This module is **not** an async-job handler — there is no
``handle_pr_narrow_synthesis``. The Phase-4 design wrapped this in a
separate ``JOB_PR_NARROW_SYNTHESIS`` so the dispatcher could enqueue
and return; Phase 5 collapses dispatcher + narrow synth into one
worker (the per-(org, repo) Redis-stream consumer) so the lock-handoff
race between them is structurally impossible.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any

import structlog
from sqlalchemy.exc import SQLAlchemyError

from app.config import settings as app_settings
from app.database import AsyncSessionLocal
from app.mcp.auth import create_internal_mcp_token
from app.mcp.synthesis_accumulator import drain, reset_for_org
from app.repositories.feature import FeatureRepository
from app.repositories.feature_match_log import FeatureMatchLogRepository
from app.repositories.feature_to_repo import list_features_with_backend_link_to
from app.repositories.tracked_repository import TrackedRepoRepository
from app.services.feature_reconciler import reconcile_features_for_repo
from app.services.scan.backend_link.narrow_refresh import (
    refresh_backend_links_for_features,
)
from app.services.scan.backend_link.route_index import index_and_cache_backend_routes
from app.services.scan.pr_narrow_loader import (
    load_existing_features_by_sig,
    load_scoped_communities,
)
from app.services.scan.synthesis.narrow_prompt import build_narrow_synthesis_prompt
from app.services.scan.synthesis.runner import (
    DEFAULT_MAX_TURNS,
    DEFAULT_MODEL,
    DEFAULT_TIMEOUT_SECONDS,
    ClaudeCodeEngine,
    SynthesisRequest,
)

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class NarrowSynthesisParams:
    """Parsed parameters for one narrow-synthesis run.

    The dispatcher constructs this from the WebhookLog row's payload
    and the cluster-diff result; the worker passes it through to
    :func:`run_narrow_synthesis` without further validation.
    """

    org_id: uuid.UUID
    repo_id: uuid.UUID
    pr_number: int
    base_sha: str
    head_sha: str
    full_name: str
    affected_signatures: list[str]


@dataclass(frozen=True, slots=True)
class NarrowSynthesisOutcome:
    """Result summary returned to the caller for telemetry.

    ``branch`` is one of ``"empty"`` (no clusters resolved at either
    SHA — no-op), ``"deletion"`` (pure-deletion, LLM skipped),
    ``"synthesised"`` (Claude ran). On failure ``error`` is populated.
    """

    branch: str
    inserted: int = 0
    updated: int = 0
    revived: int = 0
    inactivated: int = 0
    error: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.error is None


async def run_narrow_synthesis(params: NarrowSynthesisParams) -> NarrowSynthesisOutcome:
    """Run one narrow-synthesis pass; return a summary outcome.

    Raises on the IO failure paths (DB unreachable, MCP unconfigured,
    repo row missing) so the calling worker can flip the WebhookLog
    row to ``failed`` and surface the error to operators. The Claude
    run itself is a softer failure: ``outcome.error`` is populated and
    the accumulator is reset, but no exception is raised — the dispatch
    layer treats that as a recoverable per-delivery failure.
    """
    async with AsyncSessionLocal() as db:
        repo = await TrackedRepoRepository(db, org_id=params.org_id).get_by_id(params.repo_id)
        if repo is None or not repo.path:
            logger.warning(
                "pr_narrow_synthesis_repo_missing",
                org_id=str(params.org_id),
                repo_id=str(params.repo_id),
            )
            return NarrowSynthesisOutcome(branch="empty")

        communities, signatures, affected_files = await load_scoped_communities(
            db,
            org_id=params.org_id,
            repo_id=params.repo_id,
            base_sha=params.base_sha,
            head_sha=params.head_sha,
            affected_signatures=params.affected_signatures,
        )
        existing_by_sig = await load_existing_features_by_sig(
            db, org_id=params.org_id, repo_id=params.repo_id, signatures=signatures
        )

    if not signatures:
        logger.info(
            "pr_narrow_synthesis_no_clusters_at_either_sha",
            repo_id=str(params.repo_id),
            head_sha=params.head_sha[:8],
            requested=len(params.affected_signatures),
        )
        return NarrowSynthesisOutcome(branch="empty")

    if not communities:
        # Pure-deletion branch: every affected cluster is in
        # ``signatures`` from BASE_SHA only — nothing survives at
        # head, so Claude has nothing to look at. Skip the LLM
        # call and go straight to reconcile: the existing feature
        # whose ``cluster_signature`` matches lands in the scoped
        # candidate pool, no synthesised write claims it, and the
        # reconciler soft-deletes it with ``deactivated_at_sha``.
        logger.info(
            "pr_narrow_synthesis_pure_deletion",
            repo_id=str(params.repo_id),
            head_sha=params.head_sha[:8],
            removed_signatures=len(signatures),
        )
        summary = await _reconcile_narrow(
            org_id=params.org_id,
            repo_id=params.repo_id,
            head_sha=params.head_sha,
            signatures=signatures,
            affected_files=affected_files,
        )
        await _refresh_backend_links_post_reconcile(
            org_id=params.org_id,
            repo_id=params.repo_id,
            signatures=signatures,
            affected_files=affected_files,
        )
        await _refresh_cross_layer_from_backend_merge(
            org_id=params.org_id, repo_id=params.repo_id, head_sha=params.head_sha
        )
        logger.info(
            "pr_narrow_synthesis_done",
            repo_id=str(params.repo_id),
            head_sha=params.head_sha[:8],
            **summary,
        )
        return NarrowSynthesisOutcome(
            branch="deletion",
            inserted=summary["inserted"],
            updated=summary["updated"],
            revived=summary["revived"],
            inactivated=summary["inactivated"],
        )

    prompt = build_narrow_synthesis_prompt(
        repo_name=repo.github_repo_full_name or repo.path,
        communities=communities,
        existing_by_signature=existing_by_sig,
        repo_id=str(params.repo_id),
    )
    outcome = await _run_claude_narrow(
        org_id=params.org_id,
        prompt=prompt,
        repo_path=repo.path,
        repo_name=repo.github_repo_full_name or repo.path,
    )
    if not outcome["success"]:
        reset_for_org(str(params.org_id))
        return NarrowSynthesisOutcome(
            branch="synthesised",
            error=outcome.get("error") or "narrow synthesis failed",
        )

    summary = await _reconcile_narrow(
        org_id=params.org_id,
        repo_id=params.repo_id,
        head_sha=params.head_sha,
        signatures=signatures,
        affected_files=affected_files,
    )
    await _refresh_backend_links_post_reconcile(
        org_id=params.org_id,
        repo_id=params.repo_id,
        signatures=signatures,
        affected_files=affected_files,
    )
    await _refresh_cross_layer_from_backend_merge(
        org_id=params.org_id, repo_id=params.repo_id, head_sha=params.head_sha
    )
    logger.info(
        "pr_narrow_synthesis_done",
        repo_id=str(params.repo_id),
        head_sha=params.head_sha[:8],
        **summary,
    )
    return NarrowSynthesisOutcome(
        branch="synthesised",
        inserted=summary["inserted"],
        updated=summary["updated"],
        revived=summary["revived"],
        inactivated=summary["inactivated"],
    )


async def _run_claude_narrow(
    *,
    org_id: uuid.UUID,
    prompt: str,
    repo_path: str,
    repo_name: str,
) -> dict[str, Any]:
    """Resolve the engine and run one Claude pass over the narrow prompt.

    Mirrors the synthesize stage's invocation pattern but without the
    scan-runtime plumbing (progress callback, dry-run, tool counters).
    """
    if not app_settings.mcp_backend_url:
        logger.warning("pr_narrow_synthesis_no_mcp_backend_url", org_id=str(org_id))
        return {"success": False, "error": "mcp_backend_url not configured"}
    token = create_internal_mcp_token(org_id)
    request = SynthesisRequest(
        prompt=prompt,
        working_dir=repo_path,
        repo_name=repo_name,
        mcp_backend_url=app_settings.mcp_backend_url,
        mcp_token=token,
        model=DEFAULT_MODEL,
        max_turns=DEFAULT_MAX_TURNS,
        timeout_seconds=DEFAULT_TIMEOUT_SECONDS,
        progress_callback=None,
    )
    t0 = time.perf_counter()
    outcome = await ClaudeCodeEngine().run(request)
    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    logger.info(
        "pr_narrow_synthesis_claude_done",
        org_id=str(org_id),
        success=outcome.success,
        elapsed_ms=elapsed_ms,
        cost_usd=outcome.cost_usd,
        error=outcome.error[:200] if outcome.error else None,
    )
    return {
        "success": outcome.success,
        "elapsed_ms": elapsed_ms,
        "cost_usd": outcome.cost_usd,
        "error": outcome.error,
    }


NARROW_BACKEND_LINK_FEATURE_CAP = 20


async def _refresh_backend_links_post_reconcile(
    *,
    org_id: uuid.UUID,
    repo_id: uuid.UUID,
    signatures: set[str],
    affected_files: set[str],
) -> None:
    """Refresh cross-repo BACKEND junctions for features touched by this PR.

    Runs after :func:`_reconcile_narrow`. Cross-layer junctions don't
    affect the local reconcile outcome, so any failure is swallowed
    (logged via ``narrow_backend_link_refresh_failed``) — operator can
    inspect and a future full scan will heal whatever this missed.

    Feature lookup admits BOTH signature matches and file-overlap
    matches (via ``affected_files``). The file-overlap fallback is
    necessary because feature rows store a ``cluster_signature``
    snapshotted at synthesis time — the indexer's clustering
    algorithm has changed across releases, so a feature whose files
    were touched by this PR may carry a stale signature that no
    longer appears in the current cluster_cache. Without the
    fallback, the reconciler would correctly update such a feature
    (via its own file-overlap path) but the cross-layer refresh would
    miss it, leaving the BACKEND junction inconsistent with the
    feature's new code_locations.

    Scope guard: capped at :data:`NARROW_BACKEND_LINK_FEATURE_CAP` to
    keep the per-merge cost bounded. Bigger affected sets fall through
    to the next full scan's global ``backend_link`` phase.
    """
    try:
        async with AsyncSessionLocal() as db:
            feat_repo = FeatureRepository(db, org_id=org_id)
            feature_ids = await feat_repo.list_active_ids_by_signatures(
                repo_id, signatures, affected_files=affected_files
            )
            if not feature_ids:
                return
            if len(feature_ids) > NARROW_BACKEND_LINK_FEATURE_CAP:
                logger.info(
                    "narrow_backend_link_refresh_skipped_above_cap",
                    repo_id=str(repo_id),
                    count=len(feature_ids),
                    cap=NARROW_BACKEND_LINK_FEATURE_CAP,
                )
                return
            await refresh_backend_links_for_features(db, org_id=org_id, feature_ids=feature_ids)
    except (SQLAlchemyError, OSError):
        # DB / filesystem failures are operationally recoverable — next
        # full scan heals the cross-layer state. Programmer errors
        # (AttributeError, TypeError, KeyError) intentionally propagate
        # so a refactor that breaks the helper signature fails loudly
        # in CI rather than getting silently swallowed.
        logger.exception("narrow_backend_link_refresh_failed", repo_id=str(repo_id))


async def _refresh_cross_layer_from_backend_merge(
    *, org_id: uuid.UUID, repo_id: uuid.UUID, head_sha: str
) -> None:
    """Backend-side cross-layer refresh after a backend repo's PR merge.

    Counterpart to :func:`_refresh_backend_links_post_reconcile`:

    * The frontend-side helper above handles "the merged-repo's own
      affected features need their api_paths rechecked" — i.e., it
      refreshes BACKEND junctions whose *source* feature is in the
      merged repo.
    * THIS helper handles "frontend features that already point AT
      this repo need their api_paths rechecked" — i.e., when a backend
      repo's routes change (renamed, removed, or added), the frontend
      features whose BACKEND junctions land here are the only ones
      whose api_paths set may legitimately need to shrink (path went
      away) or grow (new path now matches an existing fetch). The
      "frontend fetch is new" case is out of scope here — Phase 5
      intentionally defers it (see plan handoff).

    Two coordinated steps inside one helper:

    1. Backfill ``backend_route_cache`` for ``(repo_id, head_sha)`` AND
       advance ``tracked_repositories.head_sha`` so the global index
       builder reads from the fresh rows (see
       :func:`index_and_cache_backend_routes`). No-op on non-backend
       repos.
    2. List frontend feature_ids with an existing BACKEND junction
       here, then run :func:`refresh_backend_links_for_features` on
       them — bounded by :data:`NARROW_BACKEND_LINK_FEATURE_CAP` to
       cap per-merge cost.

    All failures swallowed + logged: cross-layer state isn't required
    for the local reconcile to be correct, and the next full scan
    heals whatever this misses.
    """
    try:
        written = await index_and_cache_backend_routes(
            org_id=org_id, repo_id=repo_id, head_sha=head_sha
        )
    except (SQLAlchemyError, OSError):
        # Worktree-walk + cache write failure — the route extractor
        # touches disk and Postgres. Other exception types
        # (programmer errors) intentionally propagate.
        logger.exception(
            "narrow_route_index_failed",
            repo_id=str(repo_id),
            head_sha=head_sha[:8],
        )
        return
    if written == 0:
        # Non-backend repo, cache already hot for this SHA, or no
        # routes found. Either way: no frontend features could newly
        # need a refresh on the basis of THIS merge, so skip the
        # second step too.
        return

    try:
        async with AsyncSessionLocal() as db:
            feature_ids = await list_features_with_backend_link_to(
                db, org_id=org_id, backend_repo_id=repo_id
            )
            if not feature_ids:
                return
            if len(feature_ids) > NARROW_BACKEND_LINK_FEATURE_CAP:
                logger.info(
                    "narrow_cross_layer_from_backend_skipped_above_cap",
                    repo_id=str(repo_id),
                    count=len(feature_ids),
                    cap=NARROW_BACKEND_LINK_FEATURE_CAP,
                )
                return
            await refresh_backend_links_for_features(db, org_id=org_id, feature_ids=feature_ids)
    except (SQLAlchemyError, OSError):
        logger.exception("narrow_cross_layer_from_backend_failed", repo_id=str(repo_id))


async def _reconcile_narrow(
    *,
    org_id: uuid.UUID,
    repo_id: uuid.UUID,
    head_sha: str,
    signatures: set[str],
    affected_files: set[str],
) -> dict[str, int]:
    """Drain the per-repo accumulator and reconcile scoped to the PR.

    The ``candidate_filter`` admits a feature into the scope when
    EITHER condition holds:

    * its ``cluster_signature`` matches one of the affected signatures
      (primary identity — the indexer's current view of the cluster);
    * its ``code_locations`` files intersect any affected cluster's
      files (Jaccard fallback — the indexer's signature algorithm has
      changed across releases, so legacy features have stale
      ``cluster_signature`` values that don't match the current
      indexer output even though they still describe the same cluster
      files). Without this fallback, a deletion PR can't reach the
      legacy feature to soft-delete it, and orphan rows accumulate.

    Features outside both checks stay immune to soft-delete — the
    per-PR scoping property is preserved.
    """
    synthesised = drain(str(org_id), str(repo_id))

    def _in_scope(c: Any) -> bool:
        if c.cluster_signature in signatures:
            return True
        # Flatten ``{"frontend": [...], "backend": [...]}`` into a flat
        # set of paths and check overlap with the affected file set.
        cl = c.code_locations or {}
        feat_files: set[str] = set()
        for value in cl.values():
            if isinstance(value, list):
                feat_files.update(p for p in value if isinstance(p, str))
        return bool(feat_files & affected_files)

    async with AsyncSessionLocal() as db:
        summary = await reconcile_features_for_repo(
            db=db,
            org_id=org_id,
            repo_id=repo_id,
            head_sha=head_sha,
            synthesised=synthesised,
            candidate_filter=_in_scope,
        )
        if summary.match_log_rows:
            await FeatureMatchLogRepository(db, org_id=org_id).bulk_insert(summary.match_log_rows)
        await db.commit()
    return {
        "inserted": summary.inserted,
        "updated": summary.updated,
        "revived": summary.revived,
        "inactivated": summary.inactivated,
    }
