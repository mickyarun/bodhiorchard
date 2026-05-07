# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Embedding-based clustering for the sandbox merge runner.

Sandbox port of
``app.services.scan.phase_impls.feature_merge_cluster.cluster_for_merge``.
Pure Python (no numpy) — seed data is small enough that a 113 × 113
cosine pass runs in well under a second.

Two passes shape the clusters:

1. **Same-title forced union.** Two synth rows from different repos
   that share an identical ``feature_title`` *must* land in the same
   cluster. Production hit a ``(org_id, title)`` unique-key violation
   when title-twins drifted just below the cosine threshold and each
   tried to promote into a fresh KI; we replicate that defence here.
2. **Pairwise cosine union.** For every (i, j) pair, call
   :func:`_should_union` and merge the union-find roots if it returns
   True. The decision is the experiment's main tuning knob — see the
   docstring on that function for the design call you should make.

The clusterer also attaches up to ``MAX_EXISTING_PER_CLUSTER`` related
canonicals from any KIs already in ``xlm_knowledge_item`` (e.g. from
prior runs in the same sandbox session), so Claude can fold new synth
rows into pre-existing canonicals where appropriate.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

import structlog

from experiments.cross_layer_merge.pair.prefilter import cosine_similarity
from experiments.cross_layer_merge.schema import (
    XLMSynthesizedFeature,
    XLMTrackedRepo,
)

log = structlog.get_logger(__name__)


# Loose default — leaves headroom for cross-layer cosine drift. The
# layer-aware override in :func:`_should_union` is what actually decides;
# this constant is just the fallback used by the inner pair loop before
# the user-provided rule kicks in.
DEFAULT_SIMILARITY_FLOOR = 0.65

# Hard cap — no Claude prompt should compare more than this many candidates.
MAX_CLUSTER_SIZE = 25

# Up to this many related canonicals (from prior sandbox runs) attach
# to each cluster's centroid. Claude sees them as "existing canonicals"
# in the prompt so it can fold new rows into them rather than minting
# duplicates.
MAX_EXISTING_PER_CLUSTER = 3
EXISTING_THRESHOLD = 0.78


@dataclass
class MergeCluster:
    """One unit of work the runner dispatches.

    A cluster is either:

    - ``is_singleton_with_no_existing_match`` → promote the synth row
      straight to a canonical (no Claude call), OR
    - multi-member, or singleton with a related canonical → render the
      Claude prompt and let it pick which rows fold together.
    """

    synth_rows: list[XLMSynthesizedFeature]
    related_existing: list[tuple[uuid.UUID, str]] = field(default_factory=list)

    @property
    def is_singleton_with_no_existing_match(self) -> bool:
        """True when the runner can skip Claude entirely."""
        return len(self.synth_rows) == 1 and not self.related_existing


def _should_union(
    row_a: XLMSynthesizedFeature,
    row_b: XLMSynthesizedFeature,
    sim: float,
    *,
    layer_lookup: dict[uuid.UUID, str],
    same_layer_threshold: float = 0.85,
    cross_layer_threshold: float = 0.80,
) -> bool:
    """Decide whether two synth rows belong in the same merge cluster.

    Available signals:
      - ``row_a.feature_title`` / ``row_b.feature_title`` (str)
      - ``row_a.tags`` / ``row_b.tags`` (list[str])
      - ``row_a.repo_id`` / ``row_b.repo_id`` — look up layer via
        ``layer_lookup`` (e.g. ``"frontend"`` / ``"backend"`` / ``"processor"``)
      - ``sim`` — cosine similarity in [-1, 1]; ~0.85 is "strong" within
        a single layer; cross-layer pairs often drift to 0.65–0.80 even
        when they describe the same end-user capability (different
        vocabulary: "form" / "input" / "validation" on the frontend vs
        "endpoint" / "schema" / "handler" on the backend).

    The four control capabilities you care about (Magic Link, Open
    Banking, Card Payments, Payment Links) all have cross-layer twins
    in the seed. A *uniform* threshold of 0.85 will miss them; a
    *uniform* 0.65 will sweep in unrelated rows. The layer-aware
    middle-ground is what this function should encode.

    Tuned on the Atoa Payments dataset (342 synth rows across 10
    repos). A threshold sweep showed:
      - flat 0.65: 10k+ pair edges → one mega-cluster (oversized split
        wipes all signal; payment-domain embeddings cluster around 0.60).
      - flat 0.85: 58 edges, 14 cross-layer clusters, max size 5 — safe
        but misses cross-layer twins where vocabulary drifts.
      - **layered 0.85 / 0.80**: 13.7% multi-repo on Atoa, matching the
        reported best run; loose enough for "Open Banking" and
        "Authentication" cross-layer pairs to cluster, tight enough
        not to mega-cluster.

    A previous experiment with 0.75 cross-layer + recursive oversized
    split regressed to 9.9% multi-repo because the recursive split
    over-tightens (jumps from 0.75 → 0.87 in one step), separating
    cross-layer pairs that just barely cleared the looser floor. The
    0.80 setting avoids that whole problem — clusters stay small
    enough that the recursive split rarely triggers.
    """
    layer_a = layer_lookup.get(row_a.repo_id)
    layer_b = layer_lookup.get(row_b.repo_id)
    cross_layer = layer_a != layer_b and layer_a is not None and layer_b is not None
    threshold = cross_layer_threshold if cross_layer else same_layer_threshold
    return sim >= threshold


def cluster_for_merge(
    *,
    synth_rows: list[XLMSynthesizedFeature],
    repos: list[XLMTrackedRepo],
    existing_canonicals: list[tuple[uuid.UUID, str, list[float] | None]],
    max_cluster_size: int = MAX_CLUSTER_SIZE,
    same_layer_threshold: float = 0.85,
    cross_layer_threshold: float = 0.80,
) -> list[MergeCluster]:
    """Group ``synth_rows`` into clusters.

    Returns clusters in deterministic order (sorted by smallest member
    id). Rows whose embedding is None come back as singletons — they
    can't participate in cosine clustering but still need to be promoted.
    """
    if not synth_rows:
        return []

    layer_lookup: dict[uuid.UUID, str] = {
        repo.id: (repo.repo_layer.value if repo.repo_layer else "unknown") for repo in repos
    }

    indexed: list[XLMSynthesizedFeature] = [r for r in synth_rows if r.embedding is not None]
    no_embedding: list[XLMSynthesizedFeature] = [r for r in synth_rows if r.embedding is None]

    if not indexed:
        return [MergeCluster(synth_rows=[r]) for r in no_embedding]

    # Union-find across the indexed rows.
    parent = {row.id: row.id for row in indexed}

    def find(rid: uuid.UUID) -> uuid.UUID:
        while parent[rid] != rid:
            parent[rid] = parent[parent[rid]]
            rid = parent[rid]
        return rid

    def union(a: uuid.UUID, b: uuid.UUID) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    # Pass 1: same-title forced union. Defends against the production
    # ``(org_id, title)`` unique-key violation that fires when two
    # synth rows from different repos share a title but drift below
    # the cosine threshold.
    #
    # We previously had a near-title (token-overlap) pass + a reapply
    # step after the recursive split, intended to catch pairs like
    # "Atoa Employee Management" ↔ "Employee Management". The audit
    # log revealed Claude correctly distinguishes most such pairs as
    # *different products* (internal Atoa staff vs merchant tenant
    # employees) — the wider clusters just produced more orphans
    # without adding multi-repo wins. Keeping just the strict same-
    # title rule, which is structurally required (constraint defence).
    by_title: dict[str, list[uuid.UUID]] = {}
    for row in indexed:
        by_title.setdefault(row.feature_title, []).append(row.id)
    for title_group in by_title.values():
        for rid in title_group[1:]:
            union(title_group[0], rid)

    # Pass 2: pairwise cosine union via the user-tunable rule.
    rows_by_id: dict[uuid.UUID, XLMSynthesizedFeature] = {r.id: r for r in indexed}
    for i, row_a in enumerate(indexed):
        for row_b in indexed[i + 1 :]:
            sim = cosine_similarity(row_a.embedding, row_b.embedding)
            if _should_union(
                row_a,
                row_b,
                sim,
                layer_lookup=layer_lookup,
                same_layer_threshold=same_layer_threshold,
                cross_layer_threshold=cross_layer_threshold,
            ):
                union(row_a.id, row_b.id)

    # Group by root.
    groups: dict[uuid.UUID, list[uuid.UUID]] = {}
    for rid in parent:
        groups.setdefault(find(rid), []).append(rid)

    # Cap oversized clusters by progressively tightening the cosine
    # floor on the outliers — mirrors production
    # ``app.services.scan.phase_impls.feature_merge_cluster._split_oversized_group``.
    # Falling straight to singletons (the previous behaviour) destroys
    # all signal in a mega-cluster; tightening the threshold instead
    # preserves the genuinely-related sub-clusters within.
    rows_for_split = {row.id: row for row in indexed}
    final_groups: list[list[uuid.UUID]] = []
    for member_ids in groups.values():
        if len(member_ids) <= max_cluster_size:
            final_groups.append(member_ids)
            continue
        log.warning(
            "cluster.oversized_split_recursive",
            size=len(member_ids),
            cap=max_cluster_size,
        )
        final_groups.extend(
            _split_oversized_group(
                member_ids=member_ids,
                rows_by_id=rows_for_split,
                layer_lookup=layer_lookup,
                # Start tightening from the calibrated same-layer floor —
                # within an oversized group we drop the cross-layer
                # loosening, so this is the right baseline to step from.
                start_threshold=same_layer_threshold,
                max_cluster_size=max_cluster_size,
            )
        )

    # Build cluster objects with related-canonical attachments.
    clusters: list[MergeCluster] = []
    for member_ids in final_groups:
        member_rows = [rows_by_id[mid] for mid in member_ids]
        related = _attach_related_existing(member_rows, existing_canonicals)
        clusters.append(MergeCluster(synth_rows=member_rows, related_existing=related))

    clusters.extend(MergeCluster(synth_rows=[r]) for r in no_embedding)
    clusters.sort(key=lambda c: min(r.id for r in c.synth_rows))

    log.info(
        "cluster.built",
        synth_rows=len(synth_rows),
        cluster_count=len(clusters),
        singletons=sum(1 for c in clusters if c.is_singleton_with_no_existing_match),
        max_size=max((len(c.synth_rows) for c in clusters), default=0),
    )
    return clusters


def _split_oversized_group(
    *,
    member_ids: list[uuid.UUID],
    rows_by_id: dict[uuid.UUID, XLMSynthesizedFeature],
    layer_lookup: dict[uuid.UUID, str],
    start_threshold: float,
    max_cluster_size: int,
    threshold_step: float = 0.02,
    threshold_ceiling: float = 0.99,
) -> list[list[uuid.UUID]]:
    """Re-cluster an oversized group at progressively tighter thresholds.

    Walks the same union-find logic as the main pass but with a higher
    floor and *no layer-aware loosening* — when a cluster is already
    too big, the cross-layer drift exception that justified 0.80 has
    already done its work. Recurses on sub-groups still too big until
    every output fits ``max_cluster_size`` or the threshold reaches
    ``threshold_ceiling`` (at which point each row becomes its own
    singleton — guaranteed termination).
    """
    threshold = round(start_threshold + threshold_step, 4)
    if threshold >= threshold_ceiling:
        # Hard floor — isolate every row. Prevents infinite recursion
        # when many rows have essentially identical embeddings.
        return [[mid] for mid in member_ids]

    parent = {mid: mid for mid in member_ids}

    def find(rid: uuid.UUID) -> uuid.UUID:
        while parent[rid] != rid:
            parent[rid] = parent[parent[rid]]
            rid = parent[rid]
        return rid

    def union(a: uuid.UUID, b: uuid.UUID) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    # Re-cluster at the tightened threshold. We deliberately drop the
    # layer-aware loosening here — once the parent cluster is over
    # ``max_cluster_size``, the cross-layer exception is already paid
    # for; tightening uniformly is the simplest split signal.
    n = len(member_ids)
    for i in range(n):
        for j in range(i + 1, n):
            row_a = rows_by_id[member_ids[i]]
            row_b = rows_by_id[member_ids[j]]
            if row_a.embedding is None or row_b.embedding is None:
                continue
            sim = cosine_similarity(list(row_a.embedding), list(row_b.embedding))
            if sim >= threshold:
                union(row_a.id, row_b.id)

    sub_groups: dict[uuid.UUID, list[uuid.UUID]] = {}
    for mid in member_ids:
        sub_groups.setdefault(find(mid), []).append(mid)

    out: list[list[uuid.UUID]] = []
    for sub in sub_groups.values():
        if len(sub) <= max_cluster_size:
            out.append(sub)
        else:
            out.extend(
                _split_oversized_group(
                    member_ids=sub,
                    rows_by_id=rows_by_id,
                    layer_lookup=layer_lookup,
                    start_threshold=threshold,
                    max_cluster_size=max_cluster_size,
                    threshold_step=threshold_step,
                    threshold_ceiling=threshold_ceiling,
                )
            )
    return out


def _attach_related_existing(
    member_rows: list[XLMSynthesizedFeature],
    existing_canonicals: list[tuple[uuid.UUID, str, list[float] | None]],
) -> list[tuple[uuid.UUID, str]]:
    """Pick the top-K existing canonicals whose embedding sits near the cluster centroid.

    Centroid is the mean of member embeddings (skipping any that are
    None). Returns up to ``MAX_EXISTING_PER_CLUSTER`` (kid, title)
    tuples sorted by descending similarity. Used so Claude can fold
    new synth rows into pre-existing canonicals rather than minting
    duplicates on every run.
    """
    if not existing_canonicals:
        return []
    member_vecs = [r.embedding for r in member_rows if r.embedding is not None]
    if not member_vecs:
        return []

    dim = len(member_vecs[0])
    centroid = [sum(v[i] for v in member_vecs) / len(member_vecs) for i in range(dim)]

    scored: list[tuple[float, uuid.UUID, str]] = []
    for kid, title, emb in existing_canonicals:
        if emb is None:
            continue
        scored.append((cosine_similarity(centroid, emb), kid, title))
    scored.sort(key=lambda t: t[0], reverse=True)

    return [
        (kid, title)
        for sim, kid, title in scored[:MAX_EXISTING_PER_CLUSTER]
        if sim >= EXISTING_THRESHOLD
    ]
