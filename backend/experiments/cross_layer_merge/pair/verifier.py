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

"""Per-pair Claude verifier — drives the prompt and applies merges.

For each PENDING ``XLMPairPlan`` row:

1. Pull canonical KIs and their backing synth rows for both repos.
2. For every source feature on ``repo_a``, prefilter top-5 candidates
   from ``repo_b`` via ``prefilter.prefilter_candidates``.
3. Render the prompt, ask Claude (``claude_client.ask_claude``), parse.
4. Log the call to ``xlm_pair_log`` (the prompt-iteration audit trail).
5. On a merge verdict, hand off to ``apply.merge_applier.apply_merge``.
6. Mark the pair DONE with ``merged_count``; FAILED on uncaught error.
"""

import asyncio
import os
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from experiments.cross_layer_merge.apply.merge_applier import apply_merge
from experiments.cross_layer_merge.pair.claude_client import ask_claude, parse_verdict
from experiments.cross_layer_merge.pair.planner import list_pending_pairs
from experiments.cross_layer_merge.pair.prefilter import (
    SourceWithSynth,
    prefilter_candidates,
)
from experiments.cross_layer_merge.prompts.verify_pair import (
    FeatureView,
    RepoView,
    build_prompt,
)
from experiments.cross_layer_merge.schema import (
    XLMKnowledgeItem,
    XLMKnowledgeRepoLink,
    XLMMergeOutcome,
    XLMPairLog,
    XLMPairPlan,
    XLMPairStatus,
    XLMSynthesizedFeature,
    XLMTrackedRepo,
)

log = structlog.get_logger(__name__)

# Each source feature within a pair gets one Claude call. Cap parallel calls
# so we don't hammer the CLI with 60+ concurrent subprocesses.
_VERIFIER_CONCURRENCY = int(os.environ.get("XLM_VERIFIER_CONCURRENCY", "8"))


async def verify_all_pending() -> dict[str, int]:
    """Run the verifier on every PENDING pair concurrently. Returns count summary."""
    pairs = await list_pending_pairs()
    sem = asyncio.Semaphore(_VERIFIER_CONCURRENCY)

    async def _run_one(pair_id: uuid.UUID) -> tuple[int, int]:
        """Returns (merges_applied, error_count)."""
        async with sem:
            try:
                merged = await _verify_one_pair(pair_id)
                return merged, 0
            except Exception:
                log.exception("verifier.pair_failed", pair_id=str(pair_id))
                await _set_pair_status(pair_id, XLMPairStatus.FAILED)
                return 0, 1

    results = await asyncio.gather(*(_run_one(p.id) for p in pairs))
    merges = sum(r[0] for r in results)
    errors = sum(r[1] for r in results)
    return {
        "pairs_processed": len(pairs) - errors,
        "merges_applied": merges,
        "errors": errors,
    }


async def _verify_one_pair(pair_id: uuid.UUID) -> int:
    """Process one pair end-to-end. Returns merges applied."""
    await _set_pair_status(pair_id, XLMPairStatus.RUNNING)

    async with AsyncSessionLocal() as session:
        pair = await session.get(XLMPairPlan, pair_id)
        if pair is None:
            raise LookupError(f"pair {pair_id} not found")
        repo_a = await session.get(XLMTrackedRepo, pair.repo_a_id)
        repo_b = await session.get(XLMTrackedRepo, pair.repo_b_id)
        if repo_a is None or repo_b is None:
            raise LookupError("one or both repos in pair not found")

        source_features = await _load_canonical_features(session, repo_a.id)
        candidate_features = await _load_canonical_features(session, repo_b.id)
        source_repo_view = _to_repo_view(repo_a)
        target_repo_view = _to_repo_view(repo_b)

    # Skip KIs that are already linked to BOTH repos in the pair — they were
    # consolidated by Stage 1 (within-layer) merge already, so re-asking
    # Claude about them produces self-merge attempts. The candidate side
    # also gets de-duped by KI to avoid showing the same row twice.
    target_ki_ids = {f.synth.knowledge_item_id for f in candidate_features}
    source_features = [
        f for f in source_features if f.synth.knowledge_item_id not in target_ki_ids
    ]
    seen_ki: set[uuid.UUID | None] = set()
    deduped_candidates: list[SourceWithSynth] = []
    for c in candidate_features:
        if c.synth.knowledge_item_id in seen_ki:
            continue
        seen_ki.add(c.synth.knowledge_item_id)
        deduped_candidates.append(c)
    candidate_features = deduped_candidates

    if not source_features or not candidate_features:
        log.info(
            "verifier.empty_pair",
            pair_id=str(pair_id),
            source_count=len(source_features),
            cand_count=len(candidate_features),
        )
        await _set_pair_status(pair_id, XLMPairStatus.DONE, merged_count=0)
        return 0

    src_sem = asyncio.Semaphore(_VERIFIER_CONCURRENCY)

    async def _verify_source(source: SourceWithSynth) -> int:
        """Ask Claude for one source feature. Returns 1 if merged, else 0."""
        candidates = prefilter_candidates(source, candidate_features)
        if not candidates:
            return 0
        prompt = build_prompt(
            source_repo=source_repo_view,
            source_feature=source.view,
            target_repo=target_repo_view,
            candidates=[c.view for c in candidates],
        )
        async with src_sem:
            response_text = await ask_claude(prompt)
        verdict = parse_verdict(response_text)
        await _record_log(
            pair_id=pair_id,
            source=source,
            candidates=candidates,
            prompt=prompt,
            response=response_text,
            verdict=verdict,
        )
        if verdict["action"] != "merge":
            return 0
        # repo_a is always frontend (enforced by planner). Force the frontend
        # source as canonical so the frontend KI survives and the backend KI
        # is deactivated + repointed — never the reverse.
        verdict_canonical = uuid.UUID(verdict["canonical_synth_id"])
        verdict_absorbs = {uuid.UUID(s) for s in verdict["absorb_synth_ids"]}
        absorb_ids = list((verdict_absorbs | {verdict_canonical}) - {source.synth.id})
        if not absorb_ids:
            log.warning("verifier.no_absorbs_after_frontend_force", source=str(source.synth.id))
            return 0
        await apply_merge(canonical_synth_id=source.synth.id, absorb_synth_ids=absorb_ids)
        return 1

    results = await asyncio.gather(*(_verify_source(s) for s in source_features))
    merged_count = sum(results)
    await _set_pair_status(pair_id, XLMPairStatus.DONE, merged_count=merged_count)
    return merged_count


async def _load_canonical_features(
    session: AsyncSession, repo_id: uuid.UUID
) -> list[SourceWithSynth]:
    """Pull every CANONICAL synth row whose KI is linked to ``repo_id``."""
    rows = (
        await session.execute(
            select(XLMSynthesizedFeature, XLMKnowledgeItem)
            .join(
                XLMKnowledgeItem,
                XLMSynthesizedFeature.knowledge_item_id == XLMKnowledgeItem.id,
            )
            .join(
                XLMKnowledgeRepoLink,
                XLMKnowledgeRepoLink.knowledge_id == XLMKnowledgeItem.id,
            )
            .where(
                XLMKnowledgeRepoLink.repo_id == repo_id,
                XLMSynthesizedFeature.merge_outcome == XLMMergeOutcome.CANONICAL,
                XLMKnowledgeItem.is_active.is_(True),
            )
            .order_by(XLMSynthesizedFeature.feature_title)
        )
    ).all()
    return [SourceWithSynth(synth=synth, view=_to_feature_view(synth)) for synth, _ in rows]


def _to_repo_view(repo: XLMTrackedRepo) -> RepoView:
    return RepoView(
        name=repo.name,
        layer=repo.repo_layer.value if repo.repo_layer else "unknown",
        tech_stack=repo.tech_stack,
    )


def _to_feature_view(synth: XLMSynthesizedFeature) -> FeatureView:
    return FeatureView(
        synth_id=str(synth.id),
        title=synth.feature_title,
        description=synth.description,
        capabilities=synth.capabilities or {},
        tags=list(synth.tags or []),
        cluster_names=list(synth.cluster_names or []),
        code_paths=_flatten_code_locations(synth.code_locations),
    )


def _flatten_code_locations(payload: dict[str, Any] | None) -> list[str]:
    """Pull a flat list of file:line strings from the per-layer JSONB shape."""
    if not payload:
        return []
    return [
        f"{layer}: {item}"
        for layer, items in payload.items()
        if isinstance(items, list)
        for item in items
    ]


async def _set_pair_status(
    pair_id: uuid.UUID,
    status: XLMPairStatus,
    *,
    merged_count: int | None = None,
    error: str | None = None,
) -> None:
    """Single state-machine writer for ``xlm_pair_plan`` row updates."""
    async with AsyncSessionLocal() as session:
        pair = await session.get(XLMPairPlan, pair_id)
        if pair is None:
            return
        pair.status = status
        now = datetime.now(UTC)
        if status == XLMPairStatus.RUNNING:
            pair.started_at = now
        if status in (XLMPairStatus.DONE, XLMPairStatus.FAILED):
            pair.finished_at = now
        if merged_count is not None:
            pair.merged_count = merged_count
        if error is not None:
            pair.error = error
        await session.commit()


async def _record_log(
    *,
    pair_id: uuid.UUID,
    source: SourceWithSynth,
    candidates: list[SourceWithSynth],
    prompt: str,
    response: str,
    verdict: dict[str, Any],
) -> None:
    async with AsyncSessionLocal() as session:
        session.add(
            XLMPairLog(
                pair_id=pair_id,
                source_synth_id=source.synth.id,
                candidate_synth_ids=[c.synth.id for c in candidates],
                prompt=prompt,
                response=response,
                action=verdict.get("action"),
                rationale=verdict.get("rationale"),
                canonical_synth_id=(
                    uuid.UUID(verdict["canonical_synth_id"])
                    if verdict.get("action") == "merge"
                    else None
                ),
                absorbed_synth_ids=[uuid.UUID(s) for s in verdict.get("absorb_synth_ids", [])],
            )
        )
        await session.commit()
