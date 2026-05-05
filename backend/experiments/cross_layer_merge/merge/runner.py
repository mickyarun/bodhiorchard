# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Sandbox merge orchestrator — mirrors ``phase_b3_merge`` shape.

Pipeline:

1. Pull every unmerged ``XLMSynthesizedFeature`` row across repos.
2. Pull every active ``XLMKnowledgeItem`` (for cluster attachment).
3. Run :func:`cluster_for_merge` to group rows by cosine + same-title.
4. Walk each cluster:
   * **Singleton, no related canonicals** → :func:`promote_synth_to_ki`
     deterministically (no Claude call).
   * **Multi-member, or singleton with related existing** → build a
     cluster prompt, ask Claude, apply the verdict.
5. Run an orphan rescue: any synth row still ``merge_outcome=NULL``
   gets promoted as a fresh canonical so the simulation always
   converges.

Returns a summary dict the CLI prints — counts and ratios so the user
can read the result without re-running ``report``.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import Awaitable
from dataclasses import dataclass
from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from experiments.cross_layer_merge.merge.applier import apply_cluster_merge
from experiments.cross_layer_merge.merge.calibrate import calibrate_thresholds
from experiments.cross_layer_merge.merge.cluster import MergeCluster, cluster_for_merge
from experiments.cross_layer_merge.merge.promote import promote_synth_to_ki
from experiments.cross_layer_merge.pair.claude_client import ask_claude, parse_verdict
from experiments.cross_layer_merge.prompts.verify_pair import (
    FeatureView,
    RepoView,
    build_cluster_prompt,
)
from experiments.cross_layer_merge.schema import (
    XLMKnowledgeItem,
    XLMMergeLog,
    XLMSynthesizedFeature,
    XLMTrackedRepo,
)

# Bounded fan-out keeps memory/RAM and Anthropic-API rate limits in check.
# Each Claude cluster spawns a `claude` subprocess (~150MB RSS), so 8 in flight
# is comfortable on a dev laptop. Singleton promotion is DB-only — much cheaper.
CLAUDE_CLUSTER_CONCURRENCY = int(os.environ.get("XLM_CLAUDE_CONCURRENCY", "8"))
SINGLETON_CONCURRENCY = int(os.environ.get("XLM_SINGLETON_CONCURRENCY", "16"))

log = structlog.get_logger(__name__)


@dataclass
class MergeRunSummary:
    """Counters surfaced back to the CLI after a run."""

    synth_rows: int
    cluster_count: int
    singletons_promoted: int
    claude_clusters: int
    claude_merges_applied: int
    orphans_rescued: int
    final_active_kis: int
    same_layer_threshold: float
    cross_layer_threshold: float


async def run_merge() -> MergeRunSummary:
    """Run the full sandbox merge end-to-end."""
    async with AsyncSessionLocal() as session:
        synth_rows, repos, existing_canonicals = await _load_inputs(session)

    if not synth_rows:
        log.info("merge.skip_no_unmerged_rows")
        return MergeRunSummary(
            synth_rows=0,
            cluster_count=0,
            singletons_promoted=0,
            claude_clusters=0,
            claude_merges_applied=0,
            orphans_rescued=0,
            final_active_kis=await _count_active_kis(),
            same_layer_threshold=0.0,
            cross_layer_threshold=0.0,
        )

    # Calibrate thresholds against this org's actual cosine distribution.
    # Hardcoded thresholds work for one dataset; calibration scales across
    # orgs without per-tenant tuning.
    calibrated = calibrate_thresholds(synth_rows=synth_rows, repos=repos)
    log.info(
        "merge.thresholds_calibrated",
        same_layer=calibrated.same_layer,
        cross_layer=calibrated.cross_layer,
        same_above=calibrated.same_above_threshold,
        cross_above=calibrated.cross_above_threshold,
    )

    clusters = cluster_for_merge(
        synth_rows=synth_rows,
        repos=repos,
        existing_canonicals=existing_canonicals,
        same_layer_threshold=calibrated.same_layer,
        cross_layer_threshold=calibrated.cross_layer,
    )

    repos_by_id = {r.id: r for r in repos}
    singleton_rows: list[XLMSynthesizedFeature] = []
    claude_clusters_to_process: list[MergeCluster] = []
    for cluster in clusters:
        if cluster.is_singleton_with_no_existing_match:
            singleton_rows.append(cluster.synth_rows[0])
        else:
            claude_clusters_to_process.append(cluster)

    # Singletons: cheap DB inserts, run them concurrently within pool budget.
    await _gather_bounded(
        [_promote_one(row) for row in singleton_rows],
        limit=SINGLETON_CONCURRENCY,
    )
    singletons_promoted = len(singleton_rows)

    # Claude clusters: each cluster operates on a disjoint set of synth rows
    # (clusterer invariant), so concurrent execution has no row-level conflicts.
    claude_results = await _gather_bounded(
        [
            _process_cluster_via_claude(cluster=c, repos_by_id=repos_by_id)
            for c in claude_clusters_to_process
        ],
        limit=CLAUDE_CLUSTER_CONCURRENCY,
    )
    claude_clusters = len(claude_clusters_to_process)
    claude_merges_applied = sum(claude_results)

    orphans_rescued = await _rescue_orphans()
    final_active_kis = await _count_active_kis()

    summary = MergeRunSummary(
        synth_rows=len(synth_rows),
        cluster_count=len(clusters),
        singletons_promoted=singletons_promoted,
        claude_clusters=claude_clusters,
        claude_merges_applied=claude_merges_applied,
        orphans_rescued=orphans_rescued,
        final_active_kis=final_active_kis,
        same_layer_threshold=calibrated.same_layer,
        cross_layer_threshold=calibrated.cross_layer,
    )
    log.info("merge.done", **summary.__dict__)
    return summary


async def _gather_bounded[T](coros: list[Awaitable[T]], *, limit: int) -> list[T]:
    """Run *coros* concurrently with at most *limit* in flight at once.

    Preserves input order on the result list (asyncio.gather semantics).
    """
    if not coros:
        return []
    sem = asyncio.Semaphore(limit)

    async def _run(coro: Awaitable[T]) -> T:
        async with sem:
            return await coro

    return list(await asyncio.gather(*(_run(c) for c in coros)))


async def _load_inputs(
    session: AsyncSession,
) -> tuple[
    list[XLMSynthesizedFeature],
    list[XLMTrackedRepo],
    list[tuple[uuid.UUID, str, list[float] | None]],
]:
    """Pull the three input sets the clusterer needs."""
    synth_rows = list(
        (
            await session.execute(
                select(XLMSynthesizedFeature)
                .where(XLMSynthesizedFeature.merge_outcome.is_(None))
                .order_by(XLMSynthesizedFeature.id)
            )
        )
        .scalars()
        .all()
    )
    repos = list((await session.execute(select(XLMTrackedRepo))).scalars().all())
    existing_rows = (
        await session.execute(
            select(XLMKnowledgeItem.id, XLMKnowledgeItem.title, XLMKnowledgeItem.embedding).where(
                XLMKnowledgeItem.is_active.is_(True),
                XLMKnowledgeItem.category == "feature_registry",
            )
        )
    ).all()
    existing_canonicals: list[tuple[uuid.UUID, str, list[float] | None]] = [
        (kid, title, list(emb) if emb is not None else None) for kid, title, emb in existing_rows
    ]
    return synth_rows, repos, existing_canonicals


async def _promote_one(synth_id_or_row: XLMSynthesizedFeature) -> None:
    """Open a fresh session, re-fetch the synth row, promote, commit."""
    async with AsyncSessionLocal() as session:
        synth = await session.get(XLMSynthesizedFeature, synth_id_or_row.id)
        if synth is None:
            log.warning("merge.promote_missing_row", synth_id=str(synth_id_or_row.id))
            return
        await promote_synth_to_ki(session=session, synth=synth)
        await session.commit()


async def _process_cluster_via_claude(
    *,
    cluster: MergeCluster,
    repos_by_id: dict[uuid.UUID, XLMTrackedRepo],
) -> int:
    """Promote the canonical, ask Claude, apply the merge plan.

    Returns the number of merges applied (0 if Claude said no_match
    or the verdict was unparseable).
    """
    canonical_synth = cluster.synth_rows[0]
    candidate_synths = cluster.synth_rows[1:]

    # Promote the canonical FIRST so absorbed rows have a KI to point at.
    async with AsyncSessionLocal() as session:
        synth = await session.get(XLMSynthesizedFeature, canonical_synth.id)
        if synth is None:
            log.warning("merge.canonical_missing", synth_id=str(canonical_synth.id))
            return 0
        canonical_ki = await promote_synth_to_ki(session=session, synth=synth)
        await session.commit()
        canonical_ki_id = canonical_ki.id

    if not candidate_synths and not cluster.related_existing:
        # Singleton with no candidates and no related existing — already
        # covered by promote above; nothing for Claude to decide.
        return 0

    prompt = build_cluster_prompt(
        canonical_repo=_to_repo_view(repos_by_id[canonical_synth.repo_id]),
        canonical_feature=_to_feature_view(canonical_synth),
        candidates=[
            (_to_repo_view(repos_by_id[c.repo_id]), _to_feature_view(c)) for c in candidate_synths
        ],
        related_existing=[(str(kid), title) for kid, title in cluster.related_existing],
    )

    response_text: str | None = None
    verdict: dict[str, Any] = {}
    error: str | None = None
    try:
        response_text = await ask_claude(prompt)
        verdict = parse_verdict(response_text)
    except Exception as exc:
        error = str(exc)[:500]
        log.warning(
            "merge.claude_failed",
            canonical_synth=str(canonical_synth.id),
            cluster_size=len(cluster.synth_rows),
            error=error,
        )

    if error is not None or verdict.get("action") != "merge":
        await _record_merge_log(
            cluster=cluster,
            canonical_ki_id=canonical_ki_id,
            prompt=prompt,
            response=response_text,
            verdict=verdict,
            absorbed=[],
            error=error,
        )
        return 0

    absorb_ids = [uuid.UUID(s) for s in verdict.get("absorb_synth_ids", [])]
    # Defensive: trim ids that don't belong to this cluster (Claude
    # can't be trusted to stay in scope) and never absorb the canonical
    # into itself.
    cluster_ids = {r.id for r in cluster.synth_rows}
    safe_absorb_ids = [
        aid for aid in absorb_ids if aid in cluster_ids and aid != canonical_synth.id
    ]
    if not safe_absorb_ids:
        await _record_merge_log(
            cluster=cluster,
            canonical_ki_id=canonical_ki_id,
            prompt=prompt,
            response=response_text,
            verdict=verdict,
            absorbed=[],
            error=None,
        )
        return 0

    apply_error: str | None = None
    applied: list[uuid.UUID] = []
    try:
        result = await apply_cluster_merge(
            canonical_synth_id=canonical_synth.id,
            absorb_synth_ids=safe_absorb_ids,
        )
        applied = result.absorbed_synth_ids
    except Exception as exc:
        apply_error = str(exc)[:500]
        log.warning(
            "merge.apply_failed",
            canonical_synth=str(canonical_synth.id),
            error=apply_error,
        )

    await _record_merge_log(
        cluster=cluster,
        canonical_ki_id=canonical_ki_id,
        prompt=prompt,
        response=response_text,
        verdict=verdict,
        absorbed=applied,
        error=apply_error,
    )

    if apply_error is not None:
        return 0

    log.info(
        "merge.cluster_done",
        canonical_synth=str(canonical_synth.id),
        canonical_ki=str(canonical_ki_id),
        absorbed=len(applied),
    )
    return len(applied)


async def _record_merge_log(
    *,
    cluster: MergeCluster,
    canonical_ki_id: uuid.UUID,
    prompt: str,
    response: str | None,
    verdict: dict[str, Any],
    absorbed: list[uuid.UUID],
    error: str | None,
) -> None:
    """Persist one xlm_merge_log row per Claude cluster decision.

    Captures everything needed to debug a missed merge later: what
    Claude saw (prompt + cluster members), what it said (response,
    action, rationale), and what we applied (absorbed ids). The error
    field carries the first 500 chars of any exception that fired.
    """
    canonical = cluster.synth_rows[0]
    action = verdict.get("action") or ("error" if error else None)
    async with AsyncSessionLocal() as session:
        session.add(
            XLMMergeLog(
                canonical_synth_id=canonical.id,
                canonical_ki_id=canonical_ki_id,
                cluster_member_ids=[r.id for r in cluster.synth_rows],
                related_existing_ids=[kid for kid, _ in cluster.related_existing],
                prompt=prompt,
                response=response,
                action=action,
                rationale=verdict.get("rationale"),
                absorbed_synth_ids=absorbed,
                error=error,
            )
        )
        await session.commit()


async def _rescue_orphans() -> int:
    """Promote any synth row Claude's pass left unstamped.

    Mirrors ``app.services.scan.phase_impls.feature_merge._promote_orphan_rows``:
    in production a per-cluster Claude call sometimes times out before
    emitting a verdict, leaving rows stranded with ``merge_outcome=NULL``.
    Rather than fail the whole simulation, promote each leftover as a
    fresh canonical — better than losing the row.
    """
    rescued = 0
    async with AsyncSessionLocal() as session:
        leftover = list(
            (
                await session.execute(
                    select(XLMSynthesizedFeature)
                    .where(XLMSynthesizedFeature.merge_outcome.is_(None))
                    .order_by(XLMSynthesizedFeature.id)
                )
            )
            .scalars()
            .all()
        )
        if not leftover:
            return 0
        log.warning("merge.orphan_rescue_start", count=len(leftover))
        for synth in leftover:
            await promote_synth_to_ki(session=session, synth=synth)
            rescued += 1
        await session.commit()
    log.warning("merge.orphan_rescue_done", count=rescued)
    return rescued


async def _count_active_kis() -> int:
    """Cheap headcount of active feature_registry KIs for the run summary."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(func.count(XLMKnowledgeItem.id)).where(
                XLMKnowledgeItem.is_active.is_(True),
                XLMKnowledgeItem.category == "feature_registry",
            )
        )
        return int(result.scalar_one())


def _to_repo_view(repo: XLMTrackedRepo) -> RepoView:
    return RepoView(
        name=repo.name,
        layer=repo.repo_layer.value if repo.repo_layer else "unknown",
        tech_stack=repo.tech_stack,
    )


def _to_feature_view(synth: XLMSynthesizedFeature) -> FeatureView:
    code_paths = []
    for layer, items in (synth.code_locations or {}).items():
        if isinstance(items, list):
            for item in items:
                code_paths.append(f"{layer}: {item}")
    return FeatureView(
        synth_id=str(synth.id),
        title=synth.feature_title,
        description=synth.description,
        capabilities=dict(synth.capabilities or {}),
        tags=list(synth.tags or []),
        cluster_names=list(synth.cluster_names or []),
        code_paths=code_paths,
    )
