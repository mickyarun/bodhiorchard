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

"""Reconcile a synthesised feature batch against the existing active set.

The sole incremental writer for ``features`` + ``feature_to_repo`` under
the new lifecycle. Currently called from
``services/scan/stages/synthesize.py`` at the end of each per-repo
synthesis pass; the planned PR-merge webhook job will reuse the same
entrypoint.

The reconciler matches each synthesised entry to an existing row via a
layered identity strategy (cluster_signature → Jaccard ≥ 0.7 →
asymmetric containment ≥ 0.5 → embedding cosine ≥ 0.85 → reverse-
direction "absorbed" containment ≥ 0.6), then UPDATEs / ABSORBs /
REVIVEs / INSERTs accordingly. Existing active rows that nothing
matched are flipped ``is_active=False`` so removed features are
preserved (and revivable on re-introduction) rather than silently
disappearing.

Within each tier the resolver picks pairings globally by score-descending
edge order, not by write-iteration order. That avoids the failure where
an earlier write claims a candidate via a borderline match, leaving the
later write that would have been a clean pair to insert-as-new while the
displaced candidate gets swept inactive ("Cache Service ↔ Cache Service"
deactivations seen in PR-merge synthesis on large repos).

The containment tier exists for the "narrow PR adds a sub-component to
a broader feature" case: a 1-file PR re-synthesised on its own cluster
emits a tiny feature whose files are a strict subset of an existing
broader feature's files. Symmetric Jaccard misses this (the broader
feature dilutes the score) and the new title's embedding diverges from
the broader one's. When containment matches, we run a *conservative*
update via :func:`_absorb_into_existing`: the broader row's
title/description/capabilities/tags/cluster_signature/embedding are
preserved, only ``last_seen_sha`` advances and the junction's
``code_locations`` is unioned with the new files.

The absorbed tier covers the inverse direction: a re-synthesis run
merges several narrow legacy features into one broader new cluster.
The new write engulfs an old candidate's file set — ``|w ∩ c| / |c| ≥
0.6`` with a strict ``len(w) > len(c)`` guard — but Jaccard whiffs
because the union is dominated by the new write's extra files, the
containment tier skips because its asymmetry is the opposite, and
cosine misses because the LLM re-titled the merged cluster. Without
this tier the old candidate has no match and gets swept inactive even
though its code is still present and now lives inside the broader
feature. When the absorbed tier fires we route through
:func:`_absorb_into_existing` with ``which_wins="new"``: the surviving
``feature_id`` is preserved (so linked BUDs stay valid) while the
row's curated fields are refreshed to the new write's view and
``code_locations`` are unioned via :func:`upsert_primary_merge` so any
file in the old candidate that isn't in the new write is retained.

After all tiers and the multi-absorb secondary rescue, a final
file-presence preservation pass scans the still-unmatched active
candidates: when ≥70% of a candidate's files appear inside *some*
synthesised write's ``code_locations`` AND no other matched feature
already owns ≥30% jaccard of those files, the candidate's code is
still present at ``head_sha`` (just claimed by writes the matcher
couldn't tie to its identity) and the row is preserved via
``touch_last_seen`` instead of swept. This catches the failure mode
where a feature's files are *fragmented* across several new writes —
no single write engulfs ≥60% so tier 5 misses, no other tier matches
because titles/embeddings/signatures diverged, but the code is still
in the repo. The dedup guard ensures genuine duplicates (a smaller
feature whose files are now mostly owned by a larger active row) fall
through to sweep as they should.

Logging at every fork
(``match_via=signature|jaccard|containment|cosine|absorbed|preserved|insert``,
plus the chosen score) drives the threshold-tuning loop documented in
the plan.
"""

from __future__ import annotations

import math
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feature_match_log import FeatureMatchLog
from app.repositories.cluster_cache import ClusterCacheRepository
from app.repositories.feature import FeatureRepository
from app.repositories.feature_reads import FeatureReadRepository, ReconcilerCandidate
from app.repositories.feature_to_repo import upsert_primary, upsert_primary_merge

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class FeatureWrite:
    """One synthesised feature ready for reconciliation."""

    feature_title: str
    description: str
    capabilities: dict[str, Any]
    cluster_names: list[str]
    cluster_signature: str
    code_locations: dict[str, list[str]] | None
    embedding: list[float] | None
    tags: list[str]
    feature_status: str | None = None
    source_ref: str | None = None


@dataclass
class ReconcileResult:
    """Summary of one reconcile pass.

    ``matches_by_strategy`` counts match decisions by ``match_via`` value
    (``signature`` / ``jaccard`` / ``containment`` / ``cosine`` /
    ``absorbed`` / ``preserved`` / ``insert``). For most strategies the
    total equals the number of ``FeatureWrite`` entries: each write
    contributes exactly one decision. ``absorbed`` and ``preserved``
    are the exceptions — their counts include per-CANDIDATE rescues
    (secondary multi-absorb and file-presence preservation
    respectively), so the totals for those two strategies can exceed
    ``len(synthesised)`` when one new write covers several old narrow
    features.
    """

    inserted: int = 0
    updated: int = 0
    revived: int = 0
    inactivated: int = 0
    matches_by_strategy: dict[str, int] = field(default_factory=dict)
    match_log_rows: list[FeatureMatchLog] = field(default_factory=list)


# Default thresholds — keep aligned with the plan. Override at call site
# when running tuning experiments.
JACCARD_THRESHOLD = 0.7
COSINE_THRESHOLD = 0.85
# Asymmetric containment fires when at least half of the synthesised
# entry's files already live in a candidate AND the candidate is the
# larger side. Conservatively low so narrow re-synthesis can find its
# broader parent; the size guard prevents two unrelated tiny features
# from collapsing into one another.
CONTAINMENT_THRESHOLD = 0.5
# Reverse-direction containment for the "merged into broader new
# cluster" pattern: the new write absorbs ≥60% of an old candidate's
# files AND is strictly larger. Slightly higher than CONTAINMENT_THRESHOLD
# because the structural risk of a false match is higher when the new
# write is the bigger side (more candidates with partial overlap).
ABSORBED_THRESHOLD = 0.6
# Aggregate file-presence threshold for the final preservation pass:
# if ≥70% of an unmatched candidate's files appear in *any* synthesised
# write's code_locations, the code itself is still present at head_sha
# (just claimed by writes the matcher couldn't tie back to the
# candidate's identity) and the safer action is to keep the row alive
# rather than sweep it. Higher than ABSORBED_THRESHOLD (0.6) because
# coverage here is over the *aggregate* of all writes (looser
# aggregation needs a stricter threshold) and the action is gentler
# (touch_last_seen only, no metadata refresh).
PRESERVED_FILE_THRESHOLD = 0.7
# Dedup guard for the preservation pass: a candidate whose files are
# already ≥30% jaccard-overlapped by some *other* feature post-scan is
# almost certainly a duplicate (same code now owned by a real active
# row) and should fall through to the sweep instead of being preserved.
# Matches the SAFE_RESTORE / DUP_ACTIVE boundary in the file-presence
# audit script.
PRESERVED_DEDUP_JACCARD = 0.3


async def reconcile_features_for_repo(
    *,
    db: AsyncSession,
    org_id: uuid.UUID,
    repo_id: uuid.UUID,
    head_sha: str,
    synthesised: list[FeatureWrite],
    jaccard_threshold: float = JACCARD_THRESHOLD,
    cosine_threshold: float = COSINE_THRESHOLD,
    containment_threshold: float = CONTAINMENT_THRESHOLD,
    absorbed_threshold: float = ABSORBED_THRESHOLD,
    candidate_filter: Callable[[ReconcilerCandidate], bool] | None = None,
    deactivate_filter: Callable[[ReconcilerCandidate], bool] | None = None,
) -> ReconcileResult:
    """Apply ``synthesised`` to ``repo_id`` via incremental CRUD.

    Steps:

    1. Bulk-load every existing feature for ``repo_id`` (active +
       inactive) so revival is single-pass.
    2. Call :func:`_resolve_pairings` to assign each ``FeatureWrite``
       to an existing row by signature → Jaccard → containment → cosine.
       Within each tier the highest-scoring edge claims its pair first
       (global resolution, not per-write greedy).
    3. If matched via signature / Jaccard / cosine: revive (when
       inactive) + ``update_in_place`` + refresh PRIMARY junction. If
       matched via containment: ``_absorb_into_existing`` with
       ``which_wins="existing"`` — keep the broader row's metadata,
       union code_locations. If matched via absorbed:
       ``_absorb_into_existing`` with ``which_wins="new"`` — preserve
       the surviving ``feature_id`` but refresh the row's curated
       fields to the new write's view (so linked BUDs stay valid while
       title/description/embedding reflect the merged cluster), with
       code_locations still unioned. If not matched: ``insert`` +
       create PRIMARY junction.
    4. Mark every active row that nothing matched as inactive.

    ``candidate_filter`` (optional) narrows the matching pool to a
    subset of the loaded candidates. The full-scan caller leaves it
    ``None`` (default behaviour preserved); the PR-merge narrow-
    synthesis caller passes a predicate that admits features by either
    cluster_signature in the affected set OR file overlap with the PR's
    affected files (so legacy stale-signature features stay match-
    eligible).

    ``deactivate_filter`` (optional) narrows the inactivation pool
    independently. When ``None`` it defaults to ``candidate_filter``
    (preserves the historical behaviour where matching and deactivation
    used the same pool). PR-merge narrow callers pass a stricter
    predicate — typically signature-only — so a candidate admitted to
    matching purely by file overlap is *not* subject to soft-delete
    when no synth output claims it. This prevents a 1-file PR from
    deactivating a broader feature that happened to own that file.

    Returns counts so the caller can surface "+5 added, 2 revived,
    1 removed" telemetry.
    """
    reads = FeatureReadRepository(db, org_id=org_id)
    all_candidates = await reads.bulk_load_for_reconcile(repo_id, include_inactive=True)
    candidates = (
        [c for c in all_candidates if candidate_filter(c)]
        if candidate_filter is not None
        else all_candidates
    )
    by_signature: dict[str, ReconcilerCandidate] = {c.cluster_signature: c for c in candidates}
    pairings = _resolve_pairings(
        synthesised,
        candidates,
        by_signature,
        jaccard_threshold=jaccard_threshold,
        cosine_threshold=cosine_threshold,
        containment_threshold=containment_threshold,
        absorbed_threshold=absorbed_threshold,
    )
    matched_ids: set[uuid.UUID] = set()
    feat_repo = FeatureRepository(db, org_id=org_id)
    result = ReconcileResult()

    for write, (match, match_via, score) in zip(synthesised, pairings, strict=True):
        decision: str
        if match is None:
            await _insert_new(
                feat_repo,
                db=db,
                repo_id=repo_id,
                head_sha=head_sha,
                write=write,
            )
            result.inserted += 1
            decision = "inserted"
        else:
            matched_ids.add(match.feature_id)
            was_inactive = not match.is_active
            if was_inactive:
                await feat_repo.revive(match.feature_id, last_seen_sha=head_sha)
                result.revived += 1
            if match_via in ("containment", "absorbed"):
                await _absorb_into_existing(
                    feat_repo,
                    db=db,
                    feature_id=match.feature_id,
                    repo_id=repo_id,
                    head_sha=head_sha,
                    write=write,
                    existing_title=match.feature_title,
                    which_wins="new" if match_via == "absorbed" else "existing",
                )
                decision = "revived" if was_inactive else "absorbed"
            else:
                await _update_existing(
                    feat_repo,
                    db=db,
                    feature_id=match.feature_id,
                    repo_id=repo_id,
                    head_sha=head_sha,
                    write=write,
                )
                decision = "revived" if was_inactive else "updated"
            result.updated += 1
        result.matches_by_strategy[match_via] = result.matches_by_strategy.get(match_via, 0) + 1
        result.match_log_rows.append(
            FeatureMatchLog(
                org_id=org_id,
                repo_id=repo_id,
                head_sha=head_sha,
                match_via=match_via,
                score=round(score, 4),
                feature_title=write.feature_title[:500],
                matched_feature_id=match.feature_id if match else None,
                decision=decision,
            )
        )
        logger.info(
            "reconcile_match",
            org_id=str(org_id),
            repo_id=str(repo_id),
            head_sha=head_sha[:8] if head_sha else "",
            match_via=match_via,
            score=round(score, 4),
            feature_title=write.feature_title,
            matched_id=str(match.feature_id) if match else None,
            decision=decision,
        )

    # Secondary absorbed rescue: tier 5 in ``_resolve_pairings`` claims
    # at most one candidate per new write (1:1, like every other tier).
    # The "many old narrow features merged into one broader new write"
    # case leaves the other engulfed candidates unclaimed → they would
    # be swept here. Rescue them: any unmatched active candidate whose
    # files are mostly inside ANY synthesised write — matched or
    # inserted-as-new — is preserved as a distinct feature with only
    # ``last_seen_sha`` advanced. The "any write" scope is intentional:
    # the candidate's files are still present in the codebase under
    # whichever new feature row carries them, so the candidate isn't
    # stale regardless of whether the write matched or inserted. This
    # keeps ``feature_id`` stable (so linked BUDs / external refs stay
    # valid) without inflating the candidate's metadata with files that
    # aren't really "its". match_via='absorbed' + decision='rescued'
    # makes the rescue distinguishable in the audit log from primary
    # absorbs.
    rescues = _compute_absorbed_rescues(
        synthesised, candidates, matched_ids, threshold=absorbed_threshold
    )
    for cand, score in rescues:
        await feat_repo.touch_last_seen(cand.feature_id, last_seen_sha=head_sha)
        matched_ids.add(cand.feature_id)
        result.matches_by_strategy["absorbed"] = result.matches_by_strategy.get("absorbed", 0) + 1
        result.match_log_rows.append(
            FeatureMatchLog(
                org_id=org_id,
                repo_id=repo_id,
                head_sha=head_sha,
                match_via="absorbed",
                score=round(score, 4),
                feature_title=cand.feature_title[:500],
                matched_feature_id=cand.feature_id,
                decision="rescued",
            )
        )
        logger.info(
            "reconcile_match",
            org_id=str(org_id),
            repo_id=str(repo_id),
            head_sha=head_sha[:8] if head_sha else "",
            match_via="absorbed",
            score=round(score, 4),
            feature_title=cand.feature_title,
            matched_id=str(cand.feature_id),
            decision="rescued",
        )

    # File-presence preservation pass: last-line defense against the
    # narrow-synthesis failure mode where a feature's files are
    # *fragmented* across multiple new writes — no single write engulfs
    # ≥ ABSORBED_THRESHOLD so tier 5 misses, jaccard/cosine miss because
    # the cluster decomposition / titles diverged, but the code itself
    # is still in the codebase. Aggregating across every synthesised
    # write's code_locations is the deterministic ground-truth signal
    # for "files still present". The dedup guard excludes candidates
    # whose files are now mostly owned by another active feature (real
    # duplicates that the sweep should resolve).
    # Pull the indexer's view of every file at head_sha (cluster_cache
    # rows). This is the *ground-truth* "files still in the repo" signal
    # — broader than synthesis output, since the LLM may filter some
    # indexed files out of its cluster writes (e.g., low-cohesion files
    # or files outside the synthesis's affected scope on narrow paths).
    indexed_files: set[str] = set()
    if head_sha:
        cache_repo = ClusterCacheRepository(db, org_id=org_id)
        rows = await cache_repo.list_for_repo_sha(repo_id=repo_id, head_sha=head_sha)
        for row in rows:
            for path in row.files or []:
                if isinstance(path, str):
                    indexed_files.add(path)
    preserves = _compute_file_preserved_rescues(
        synthesised,
        candidates,
        pairings,
        matched_ids,
        indexed_files=indexed_files,
        threshold=PRESERVED_FILE_THRESHOLD,
        dedup_jaccard=PRESERVED_DEDUP_JACCARD,
    )
    for cand, score in preserves:
        await feat_repo.touch_last_seen(cand.feature_id, last_seen_sha=head_sha)
        matched_ids.add(cand.feature_id)
        result.matches_by_strategy["preserved"] = (
            result.matches_by_strategy.get("preserved", 0) + 1
        )
        result.match_log_rows.append(
            FeatureMatchLog(
                org_id=org_id,
                repo_id=repo_id,
                head_sha=head_sha,
                match_via="preserved",
                score=round(score, 4),
                feature_title=cand.feature_title[:500],
                matched_feature_id=cand.feature_id,
                decision="preserved",
            )
        )
        logger.info(
            "reconcile_match",
            org_id=str(org_id),
            repo_id=str(repo_id),
            head_sha=head_sha[:8] if head_sha else "",
            match_via="preserved",
            score=round(score, 4),
            feature_title=cand.feature_title,
            matched_id=str(cand.feature_id),
            decision="preserved",
        )

    deact_pool = (
        [c for c in candidates if deactivate_filter(c)]
        if deactivate_filter is not None
        else candidates
    )
    unmatched_active = [
        c.feature_id for c in deact_pool if c.is_active and c.feature_id not in matched_ids
    ]
    if unmatched_active:
        result.inactivated = await feat_repo.mark_inactive(unmatched_active, head_sha=head_sha)
    logger.info(
        "reconcile_done",
        org_id=str(org_id),
        repo_id=str(repo_id),
        head_sha=head_sha[:8] if head_sha else "",
        inserted=result.inserted,
        updated=result.updated,
        revived=result.revived,
        inactivated=result.inactivated,
    )
    return result


async def _insert_new(
    feat_repo: FeatureRepository,
    *,
    db: AsyncSession,
    repo_id: uuid.UUID,
    head_sha: str,
    write: FeatureWrite,
) -> None:
    """Insert a new feature row + PRIMARY junction in one transaction.

    Stamps both ``last_seen_sha`` and ``created_at_sha`` to ``head_sha``
    so the row carries its birth SHA forward. ``created_at_sha`` never
    changes after this; ``last_seen_sha`` advances on every reconcile
    that re-confirms the feature. The Features API joins both against
    ``pull_requests.merge_commit_sha`` to surface "Created by PR #N"
    and "Last touched by PR #M" on the card.
    """
    feature = await feat_repo.insert(
        feature_title=write.feature_title,
        description=write.description,
        capabilities=write.capabilities,
        cluster_names=list(write.cluster_names),
        cluster_signature=write.cluster_signature,
        tags=list(write.tags),
        embedding=write.embedding,
        source="scan",
        source_ref=write.source_ref,
        feature_status=write.feature_status,
        last_seen_sha=head_sha,
        created_at_sha=head_sha,
    )
    await upsert_primary(
        db,
        feature_id=feature.id,
        repo_id=repo_id,
        feature_title=write.feature_title,
        code_locations=dict(write.code_locations or {}),
    )


async def _absorb_into_existing(
    feat_repo: FeatureRepository,
    *,
    db: AsyncSession,
    feature_id: uuid.UUID,
    repo_id: uuid.UUID,
    head_sha: str,
    write: FeatureWrite,
    existing_title: str,
    which_wins: Literal["existing", "new"] = "existing",
) -> None:
    """Absorb a synth output into an existing row, preserving the feature_id.

    Two callers, distinguished by ``which_wins``:

    * ``"existing"`` — containment-tier match. The synth's files are
      mostly contained in a *larger* existing candidate. Preserve every
      curated field on the broader row (title, description,
      capabilities, tags, cluster names + signature, embedding); only
      advance ``last_seen_sha`` (so the Features API can render "Last
      touched by PR #N" against the merging commit) and union the
      synth's files into the PRIMARY junction's ``code_locations``.

    * ``"new"`` — absorbed-tier match. The new write engulfs a *smaller*
      existing candidate (legacy narrow feature merged into a broader
      new cluster). Refresh the row's curated fields to the new write's
      view via ``update_in_place`` — the surviving ``feature_id``
      remains stable so linked BUDs / external references stay valid,
      but title / description / capabilities / tags / cluster_signature
      / cluster_names / embedding all advance. ``code_locations`` are
      still unioned via :func:`upsert_primary_merge` so any file on the
      old candidate that the new write doesn't include is retained.

    Both branches end with the same merging junction upsert; what
    differs is whether the parent ``features`` row receives a
    metadata refresh first. The junction's denormalised
    ``feature_title`` mirrors the surviving row's title — i.e.
    ``existing_title`` for ``"existing"`` and ``write.feature_title``
    for ``"new"``.
    """
    if which_wins == "new":
        await feat_repo.update_in_place(
            feature_id,
            feature_title=write.feature_title,
            description=write.description,
            capabilities=write.capabilities,
            cluster_names=list(write.cluster_names),
            cluster_signature=write.cluster_signature,
            tags=list(write.tags),
            embedding=write.embedding,
            last_seen_sha=head_sha,
            feature_status=write.feature_status,
        )
        junction_title = write.feature_title
    else:
        await feat_repo.touch_last_seen(feature_id, last_seen_sha=head_sha)
        junction_title = existing_title
    await upsert_primary_merge(
        db,
        feature_id=feature_id,
        repo_id=repo_id,
        feature_title=junction_title,
        code_locations=dict(write.code_locations or {}),
    )


async def _update_existing(
    feat_repo: FeatureRepository,
    *,
    db: AsyncSession,
    feature_id: uuid.UUID,
    repo_id: uuid.UUID,
    head_sha: str,
    write: FeatureWrite,
) -> None:
    """Refresh feature fields + PRIMARY junction code_locations."""
    # Latest write's cluster_names wins; surfaces during threshold tuning
    # if it masks missed clusters.
    await feat_repo.update_in_place(
        feature_id,
        feature_title=write.feature_title,
        description=write.description,
        capabilities=write.capabilities,
        cluster_names=list(write.cluster_names),
        cluster_signature=write.cluster_signature,
        tags=list(write.tags),
        embedding=write.embedding,
        last_seen_sha=head_sha,
        feature_status=write.feature_status,
    )
    await upsert_primary(
        db,
        feature_id=feature_id,
        repo_id=repo_id,
        feature_title=write.feature_title,
        code_locations=dict(write.code_locations or {}),
    )


# O(n*m) per tier — fine at hundreds; revisit at 5k+ features per repo.
def _resolve_pairings(
    synthesised: list[FeatureWrite],
    candidates: list[ReconcilerCandidate],
    by_signature: dict[str, ReconcilerCandidate],
    *,
    jaccard_threshold: float,
    cosine_threshold: float,
    containment_threshold: float,
    absorbed_threshold: float,
) -> list[tuple[ReconcilerCandidate | None, str, float]]:
    """Globally resolve write→candidate pairings, tier-then-score order.

    Tier priority is signature → Jaccard → containment → cosine →
    absorbed. Within each tier the resolver claims the highest-scoring
    (write, candidate) edge first, then the next, until no candidate
    edges remain — instead of resolving each write in input order and
    letting the first write that walks the candidate list win.

    The old per-write greedy left "Cache Service ↔ Cache Service" pairs
    unmatched whenever a sibling write reached the candidate first via a
    borderline Jaccard. The displaced candidate then had no match and
    was swept inactive. Score-descending within-tier resolution gives
    the strongest pair first dibs on the candidate.

    The absorbed tier is the mirror image of containment: it fires when
    the new write engulfs a smaller candidate (``|w ∩ c| / |c| ≥
    absorbed_threshold`` with ``len(w) > len(c)``). This catches the
    "old narrow feature merged into a broader new cluster" pattern that
    Jaccard misses (the union is dominated by the write's extra files),
    containment skips (its asymmetry runs the other way), and cosine
    misses (the LLM re-titled the merged cluster).

    Returns one ``(candidate, match_via, score)`` per synthesised entry,
    in input order. ``match_via=='insert'`` and ``candidate is None``
    when no tier claimed the write.
    """
    n = len(synthesised)
    pairings: list[tuple[ReconcilerCandidate | None, str, float]] = [(None, "insert", 0.0)] * n
    claimed_writes: set[int] = set()
    claimed_candidates: set[uuid.UUID] = set()

    # Tier 1: signature — exact cluster_signature, 1:1 by definition.
    for i, write in enumerate(synthesised):
        cand = by_signature.get(write.cluster_signature)
        if cand is not None and cand.feature_id not in claimed_candidates:
            pairings[i] = (cand, "signature", 1.0)
            claimed_writes.add(i)
            claimed_candidates.add(cand.feature_id)

    # Memoise flattened paths so each side is built once across tiers.
    write_paths_memo: dict[int, set[str]] = {}
    cand_paths_memo: dict[uuid.UUID, set[str]] = {}

    def write_paths(i: int) -> set[str]:
        cached = write_paths_memo.get(i)
        if cached is None:
            cached = _flatten_paths(synthesised[i].code_locations)
            write_paths_memo[i] = cached
        return cached

    def cand_paths(c: ReconcilerCandidate) -> set[str]:
        cached = cand_paths_memo.get(c.feature_id)
        if cached is None:
            cached = _flatten_paths(c.code_locations)
            cand_paths_memo[c.feature_id] = cached
        return cached

    def assign_tier(
        edges: list[tuple[float, int, ReconcilerCandidate]],
        label: str,
    ) -> None:
        # Sort key, in order: score descending; lower write index wins
        # on ties (matches the old greedy by-iteration-order semantics);
        # candidate feature_id as the final deterministic tiebreak so
        # output never depends on the candidate-list order the upstream
        # loader happens to produce.
        edges.sort(key=lambda e: (-e[0], e[1], str(e[2].feature_id)))
        for score, i, cand in edges:
            if i in claimed_writes or cand.feature_id in claimed_candidates:
                continue
            pairings[i] = (cand, label, score)
            claimed_writes.add(i)
            claimed_candidates.add(cand.feature_id)

    # Tier 2: Jaccard over file paths.
    jacc_edges: list[tuple[float, int, ReconcilerCandidate]] = []
    for i in range(n):
        if i in claimed_writes:
            continue
        wp = write_paths(i)
        if not wp:
            continue
        for cand in candidates:
            if cand.feature_id in claimed_candidates:
                continue
            cp = cand_paths(cand)
            if not cp:
                continue
            score = _jaccard(wp, cp)
            if score >= jaccard_threshold:
                jacc_edges.append((score, i, cand))
    assign_tier(jacc_edges, "jaccard")

    # Tier 3: asymmetric containment. Candidate must be strictly larger
    # — absorbing into a smaller candidate would truncate the synthesis
    # result, not the other way around.
    cont_edges: list[tuple[float, int, ReconcilerCandidate]] = []
    for i in range(n):
        if i in claimed_writes:
            continue
        wp = write_paths(i)
        if not wp:
            continue
        for cand in candidates:
            if cand.feature_id in claimed_candidates:
                continue
            cp = cand_paths(cand)
            if not cp or len(wp) >= len(cp):
                continue
            score = _containment(wp, cp)
            if score >= containment_threshold:
                cont_edges.append((score, i, cand))
    assign_tier(cont_edges, "containment")

    # Tier 4: embedding cosine.
    cos_edges: list[tuple[float, int, ReconcilerCandidate]] = []
    for i, write in enumerate(synthesised):
        if i in claimed_writes or not write.embedding:
            continue
        for cand in candidates:
            if cand.feature_id in claimed_candidates or cand.embedding is None:
                continue
            score = _cosine(write.embedding, cand.embedding)
            if score >= cosine_threshold:
                cos_edges.append((score, i, cand))
    assign_tier(cos_edges, "cosine")

    # Tier 5: reverse-direction "absorbed" containment. New write must
    # be strictly larger than the candidate — equal-size sets fall
    # through to let the upstream Jaccard tier handle them (or stay
    # unmatched if they truly are different features). Score is the
    # fraction of the OLD candidate's files retained inside the NEW
    # write: |w ∩ c| / |c|.
    abs_edges: list[tuple[float, int, ReconcilerCandidate]] = []
    for i in range(n):
        if i in claimed_writes:
            continue
        wp = write_paths(i)
        if not wp:
            continue
        for cand in candidates:
            if cand.feature_id in claimed_candidates:
                continue
            cp = cand_paths(cand)
            if not cp or len(wp) <= len(cp):
                continue
            score = _containment(cp, wp)
            if score >= absorbed_threshold:
                abs_edges.append((score, i, cand))
    assign_tier(abs_edges, "absorbed")

    return pairings


def _compute_absorbed_rescues(
    synthesised: list[FeatureWrite],
    candidates: list[ReconcilerCandidate],
    matched_ids: set[uuid.UUID],
    *,
    threshold: float,
) -> list[tuple[ReconcilerCandidate, float]]:
    """Find candidates engulfed by any synthesised write (multi-absorb rescue).

    Tier 5 in :func:`_resolve_pairings` is 1:1 per tier-resolver
    invariant. When synthesis re-clustering merges N old narrow features
    into one broader new write, only the highest-scoring (write,
    candidate) edge survives there — the other engulfed candidates would
    fall through to ``unmatched_active`` and get swept inactive. This
    pass closes that gap: any unmatched active candidate whose files are
    ≥ ``threshold`` contained in *some* synthesised write (regardless of
    whether that write matched a candidate in tiers 1-5 or was inserted
    as a new feature) is returned with its best containment score so
    the caller can ``touch_last_seen`` instead of sweeping. The
    "matched-or-inserted" scope is intentional: the candidate's files
    live on inside whichever feature row the engulfing write produces.

    Skips candidates already in ``matched_ids`` (those are primary
    matches and have already been routed). Empty file sets on either
    side disqualify the pair — no files means no containment signal.

    Returns at most one row per candidate. The score is the maximum
    containment ratio observed across any qualifying write.
    """
    out: list[tuple[ReconcilerCandidate, float]] = []
    write_paths_cache: list[set[str] | None] = [None] * len(synthesised)
    for cand in candidates:
        if not cand.is_active or cand.feature_id in matched_ids:
            continue
        cp = _flatten_paths(cand.code_locations)
        if not cp:
            continue
        best: float = 0.0
        for i, write in enumerate(synthesised):
            wp = write_paths_cache[i]
            if wp is None:
                wp = _flatten_paths(write.code_locations)
                write_paths_cache[i] = wp
            if not wp or len(wp) <= len(cp):
                continue
            score = _containment(cp, wp)
            if score >= threshold and score > best:
                best = score
        if best > 0.0:
            out.append((cand, best))
    return out


def _compute_file_preserved_rescues(
    synthesised: list[FeatureWrite],
    candidates: list[ReconcilerCandidate],
    pairings: list[tuple[ReconcilerCandidate | None, str, float]],
    matched_ids: set[uuid.UUID],
    *,
    indexed_files: set[str],
    threshold: float,
    dedup_jaccard: float,
) -> list[tuple[ReconcilerCandidate, float]]:
    """Find unmatched-active candidates whose files are still in the repo.

    File-presence signal is the union of:

    * ``indexed_files`` — every file the indexer placed into any
      cluster_cache row at ``head_sha``. Ground-truth "still in the
      codebase at this SHA", broader than synthesis output.
    * Every synthesised write's ``code_locations`` — usually a subset of
      ``indexed_files`` but kept as a fallback if a caller passes an
      empty ``indexed_files`` (e.g. tests that don't model cluster_cache).

    Rescues each unmatched-active candidate whose own files are ≥
    ``threshold`` covered by that combined set AND aren't already
    mostly owned (≥ ``dedup_jaccard`` jaccard) by another feature
    alive after this scan.

    Two guard rails:

    * Coverage threshold (``threshold``) — the candidate's code must
      still be substantially present. Less than that and the candidate
      genuinely lost code, so the sweep should fire.
    * Dedup jaccard (``dedup_jaccard``) — if some other feature alive
      post-scan (a matched candidate OR an inserted write that just
      became a new feature) overlaps the unmatched candidate's files
      heavily enough to be a true duplicate, fall through to the
      sweep. Preserving a duplicate creates a stale active row
      pointing at code another active feature already owns.

    Skips candidates already in ``matched_ids`` (already routed via
    tiers 1-5 or the absorbed secondary rescue). Empty file sets on
    either side disqualify the pair.

    Returns at most one row per candidate. Score is the actual coverage
    ratio observed (≥ ``threshold``).
    """
    write_paths: list[set[str]] = [_flatten_paths(w.code_locations) for w in synthesised]
    files_present: set[str] = set(indexed_files)
    for wp in write_paths:
        files_present |= wp
    if not files_present:
        return []

    # Build the post-scan "claimed file sets" — every feature alive after
    # this scan covers one of these footprints. A matched candidate's
    # post-scan footprint is its original code_locations UNION the matching
    # write's code_locations (the merging junction upsert grows it that
    # way). An inserted write becomes a fresh feature whose footprint is
    # exactly the write's code_locations.
    claimed_file_sets: list[set[str]] = []
    for i, (match, _via, _score) in enumerate(pairings):
        wp = write_paths[i]
        if match is None:
            if wp:
                claimed_file_sets.append(wp)
        else:
            cand_paths = _flatten_paths(match.code_locations)
            combined = cand_paths | wp
            if combined:
                claimed_file_sets.append(combined)

    out: list[tuple[ReconcilerCandidate, float]] = []
    for cand in candidates:
        if not cand.is_active or cand.feature_id in matched_ids:
            continue
        cp = _flatten_paths(cand.code_locations)
        if not cp:
            continue
        coverage = len(cp & files_present) / len(cp)
        if coverage < threshold:
            continue
        # Dedup guard: skip if any feature alive post-scan (matched
        # candidate OR inserted write) now owns most of this candidate's
        # files (genuine duplicate).
        is_dup = False
        for cf in claimed_file_sets:
            if _jaccard(cp, cf) >= dedup_jaccard:
                is_dup = True
                break
        if is_dup:
            continue
        out.append((cand, coverage))
    return out


def _flatten_paths(locations: dict[str, list[str]] | None) -> set[str]:
    """Flatten ``{frontend: [...], backend: [...]}`` into a set of paths."""
    if not locations:
        return set()
    out: set[str] = set()
    for value in locations.values():
        if isinstance(value, list):
            out.update(p for p in value if isinstance(p, str))
    return out


def _jaccard(a: set[str], b: set[str]) -> float:
    """Jaccard similarity ``|a ∩ b| / |a ∪ b|``. Returns 0 for empty input."""
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def _containment(a: set[str], b: set[str]) -> float:
    """Asymmetric containment ``|a ∩ b| / |a|``: fraction of ``a`` inside ``b``.

    Returns 0 for an empty ``a``. Unlike Jaccard, this does not penalise
    the larger side for having extra files, so it is the right signal
    for the "is ``a`` mostly contained in ``b``?" question the
    containment tier asks.
    """
    if not a:
        return 0.0
    return len(a & b) / len(a)


def _cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity ``a·b / (|a|·|b|)``. Returns 0 on length mismatch."""
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
