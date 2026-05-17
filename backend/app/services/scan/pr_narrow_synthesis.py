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

"""PR-merge narrow synthesis job.

Triggered from ``pr_merge_update`` (dispatcher cap branch) when a PR
touches a small number of clusters. Runs Claude over the affected
clusters only — handing it each cluster's currently-known feature so
it can update / insert / soft-delete (via the reconciler) against the
merge head SHA.

Concretely, the handler:

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
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any

import structlog

from app.config import settings as app_settings
from app.database import AsyncSessionLocal
from app.mcp.auth import create_internal_mcp_token
from app.mcp.synthesis_accumulator import drain, reset_for_org
from app.repositories.feature_match_log import FeatureMatchLogRepository
from app.repositories.tracked_repository import TrackedRepoRepository
from app.schemas.jobs import JobState
from app.services.feature_reconciler import reconcile_features_for_repo
from app.services.job_queue import update_job
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


async def handle_pr_narrow_synthesis(job_id: str, payload: dict[str, Any]) -> None:
    """Worker entry point for ``pr_narrow_synthesis`` jobs.

    Payload shape::

        {
            "org_id":              "<uuid>",
            "repo_id":             "<uuid>",
            "pr_number":           int,
            "base_sha":            "<sha>",
            "head_sha":            "<sha>",
            "affected_signatures": ["<sha256_hex>", ...],
            "full_name":           "<owner/repo>",
        }

    ``affected_signatures`` (not cluster_ids) — the indexer reassigns
    cluster_ids when set membership changes, so they're unstable
    identifiers across SHAs. Cluster signatures (SHA-256 of member
    node-IDs) are the stable identity.
    """
    try:
        params = _parse_payload(payload)
    except (KeyError, TypeError, ValueError) as exc:
        logger.error("pr_narrow_synthesis_bad_payload", job_id=job_id, error=str(exc))
        update_job(job_id, state=JobState.FAILED, error=f"bad payload: {exc}")
        return

    update_job(job_id, state=JobState.RUNNING, status_message="Loading affected clusters…")
    try:
        async with AsyncSessionLocal() as db:
            repo = await TrackedRepoRepository(db, org_id=params.org_id).get_by_id(params.repo_id)
            if repo is None or not repo.path:
                logger.warning(
                    "pr_narrow_synthesis_repo_missing",
                    org_id=str(params.org_id),
                    repo_id=str(params.repo_id),
                )
                update_job(job_id, state=JobState.COMPLETED, status_message="repo not tracked")
                return

            communities, signatures = await load_scoped_communities(
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
            # Nothing matched at base OR head — the dispatcher gave us
            # cluster_ids that no scan has recorded. Treat as a no-op.
            logger.info(
                "pr_narrow_synthesis_no_clusters_at_either_sha",
                repo_id=str(params.repo_id),
                head_sha=params.head_sha[:8],
                requested=len(params.affected_signatures),
            )
            update_job(
                job_id,
                state=JobState.COMPLETED,
                status_message="No affected clusters present at base or head SHA",
            )
            return

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
            )
            logger.info(
                "pr_narrow_synthesis_done",
                repo_id=str(params.repo_id),
                head_sha=params.head_sha[:8],
                **summary,
            )
            update_job(
                job_id,
                state=JobState.COMPLETED,
                status_message=(
                    f"narrow synth (deletion): "
                    f"{summary['inserted']}+ "
                    f"{summary['updated']}~ "
                    f"{summary['revived']}↺ "
                    f"{summary['inactivated']}-"
                ),
            )
            return

        prompt = build_narrow_synthesis_prompt(
            repo_name=repo.github_repo_full_name or repo.path,
            communities=communities,
            existing_by_signature=existing_by_sig,
            repo_id=str(params.repo_id),
        )
        update_job(
            job_id,
            status_message=f"Running narrow synthesis over {len(communities)} cluster(s)…",
        )
        outcome = await _run_claude_narrow(
            org_id=params.org_id,
            prompt=prompt,
            repo_path=repo.path,
            repo_name=repo.github_repo_full_name or repo.path,
        )
        if not outcome["success"]:
            reset_for_org(str(params.org_id))
            update_job(
                job_id,
                state=JobState.FAILED,
                error=outcome.get("error") or "narrow synthesis failed",
            )
            return

        summary = await _reconcile_narrow(
            org_id=params.org_id,
            repo_id=params.repo_id,
            head_sha=params.head_sha,
            signatures=signatures,
        )
        logger.info(
            "pr_narrow_synthesis_done",
            repo_id=str(params.repo_id),
            head_sha=params.head_sha[:8],
            **summary,
        )
        update_job(
            job_id,
            state=JobState.COMPLETED,
            status_message=(
                f"narrow synth: {summary['inserted']}+ "
                f"{summary['updated']}~ "
                f"{summary['revived']}↺ "
                f"{summary['inactivated']}-"
            ),
        )
    except Exception as exc:  # noqa: BLE001 — broad on purpose; logged + reported
        logger.exception("pr_narrow_synthesis_failed", job_id=job_id)
        update_job(job_id, state=JobState.FAILED, error=str(exc))


@dataclass(frozen=True, slots=True)
class _Params:
    """Parsed payload — typed value object so the handler reads cleanly."""

    org_id: uuid.UUID
    repo_id: uuid.UUID
    pr_number: int
    base_sha: str
    head_sha: str
    full_name: str
    affected_signatures: list[str]


def _parse_payload(payload: dict[str, Any]) -> _Params:
    """Lift the payload dict into a typed value object; raises on bad input.

    Accepts either ``affected_signatures`` (new) or
    ``affected_cluster_ids`` (legacy, pre-signature-refactor) for
    backwards compatibility with any in-flight jobs that may have
    been enqueued just before the dispatcher rolled forward.
    """
    sigs_raw = payload.get("affected_signatures") or payload.get("affected_cluster_ids")
    if sigs_raw is None:
        raise KeyError("affected_signatures (or legacy affected_cluster_ids)")
    return _Params(
        org_id=uuid.UUID(payload["org_id"]),
        repo_id=uuid.UUID(payload["repo_id"]),
        pr_number=int(payload["pr_number"]),
        base_sha=str(payload["base_sha"]),
        head_sha=str(payload["head_sha"]),
        full_name=str(payload["full_name"]),
        affected_signatures=[str(x) for x in sigs_raw],
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


async def _reconcile_narrow(
    *,
    org_id: uuid.UUID,
    repo_id: uuid.UUID,
    head_sha: str,
    signatures: set[str],
) -> dict[str, int]:
    """Drain the per-repo accumulator and reconcile scoped to ``signatures``.

    The ``candidate_filter`` admits only features whose
    ``cluster_signature`` is in the affected set — features outside the
    scope are immune to soft-delete even though they have no matching
    ``FeatureWrite`` in this batch.
    """
    synthesised = drain(str(org_id), str(repo_id))
    async with AsyncSessionLocal() as db:
        summary = await reconcile_features_for_repo(
            db=db,
            org_id=org_id,
            repo_id=repo_id,
            head_sha=head_sha,
            synthesised=synthesised,
            candidate_filter=lambda c: c.cluster_signature in signatures,
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


