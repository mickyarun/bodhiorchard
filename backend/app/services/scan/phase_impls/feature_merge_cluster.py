# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Embedding-based clustering for the feature merge phase.

Group unmerged ``synthesized_features`` rows by cosine similarity so
each Claude subprocess sees a focused set of likely-duplicate features
(typically 3-10 rows + 0-3 related EXISTING canonicals) instead of the
whole org-wide unmerged pool. Cluster size determines per-call cost
and merge quality — too tight and Claude misses subtle duplicates,
too loose and we're back to a big single-shot prompt.

The clusterer emits two flavours of cluster:

- **Singleton with no related EXISTING** → skip Claude entirely; the
  caller promotes the synth row directly to a canonical KI.
- **Multi-member, or singleton with related EXISTING** → send to
  Claude for a focused dedup decision via ``apply_feature_merge_plan``.

Numpy is the only heavy dep (already in the env via fastembed). For
the org's typical ~250-row scale, pairwise cosine runs in <100 ms;
SQL nearest-neighbour via pgvector wins at 1 k+ rows but isn't
needed yet.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

import numpy as np
import structlog

from app.models.synthesized_feature import SynthesizedFeature

logger = structlog.get_logger(__name__)


@dataclass
class MergeCluster:
    """One unit of work for the merge phase.

    A cluster is either dispatched to Claude (multi-member, or
    singleton with related EXISTING) or promoted directly via
    ``promote_synth_to_ki`` (singleton, no related EXISTING).
    """

    synth_rows: list[SynthesizedFeature]
    related_existing: list[tuple[uuid.UUID, str]] = field(default_factory=list)

    @property
    def is_singleton_with_no_existing_match(self) -> bool:
        """True when no Claude call is needed — direct promotion path."""
        return len(self.synth_rows) == 1 and not self.related_existing


def cluster_for_merge(
    *,
    synth_rows: list[SynthesizedFeature],
    existing_canonicals: list[tuple[uuid.UUID, str, list[float] | None]],
    sibling_threshold: float = 0.85,
    existing_threshold: float = 0.85,
    max_existing_per_cluster: int = 3,
    max_cluster_size: int = 25,
) -> list[MergeCluster]:
    """Group ``synth_rows`` into clusters by cosine similarity.

    Two-stage algorithm:

    1. **Sibling clustering** — pairwise cosine across ``synth_rows``;
       union-find merges rows whose similarity ≥ ``sibling_threshold``.
       Each connected component becomes one cluster.
    2. **EXISTING attachment** — for each cluster's centroid, find the
       top ``max_existing_per_cluster`` existing canonicals whose
       cosine similarity ≥ ``existing_threshold``. These get sent to
       Claude as candidate merge targets.

    Synth rows whose embedding is None go through as singletons with
    no EXISTING attachment (Claude will see only the row itself).

    **Cluster size cap**: feature embeddings often share boilerplate
    vocabulary (e.g., everything in a payments codebase mentions
    "payment", "merchant"), so even a tight similarity threshold can
    produce one mega-cluster that defeats the whole point of batching.
    Any cluster with > ``max_cluster_size`` members is split by raising
    the threshold and re-clustering the oversized component until each
    sub-cluster fits.

    Default thresholds (0.85) lean conservative — true semantic
    duplicates of feature descriptions cluster well above 0.9 in
    practice; 0.85 leaves headroom for paraphrasing without sweeping
    in tangentially-related rows.

    Returns clusters in deterministic order (sorted by smallest
    member's id) so logs and tests stay stable across runs.
    """
    if not synth_rows:
        return []

    # Pull embeddings into a contiguous array; track which rows lack one
    # so we can keep them as standalone singletons later.
    indexed: list[tuple[int, SynthesizedFeature, np.ndarray]] = []
    no_embedding: list[SynthesizedFeature] = []
    for idx, row in enumerate(synth_rows):
        if row.embedding is None:
            no_embedding.append(row)
            continue
        indexed.append((idx, row, np.asarray(row.embedding, dtype=np.float32)))

    if not indexed:
        return [MergeCluster(synth_rows=[r]) for r in no_embedding]

    matrix = np.stack([vec for _, _, vec in indexed])
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    normalised = matrix / norms

    # Pairwise cosine via a single matmul. For ~250 rows this is ~62k
    # entries — well under a millisecond on numpy's BLAS path.
    sim = normalised @ normalised.T

    # Union-find — siblings merge when cosine ≥ threshold.
    parent = list(range(len(indexed)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    n = len(indexed)
    # First-pass union: rows sharing the EXACT same ``feature_title``
    # always belong together regardless of embedding distance. This
    # prevents the constraint violation that fires when two same-title
    # synth rows from different repos drift just below the cosine
    # threshold and each tries to promote to a fresh KI with the
    # already-taken (org, title) key.
    by_title: dict[str, list[int]] = {}
    for idx, (_, row, _vec) in enumerate(indexed):
        by_title.setdefault(row.feature_title, []).append(idx)
    for member_indices in by_title.values():
        for i in member_indices[1:]:
            union(member_indices[0], i)

    # Second-pass union: cosine-similar siblings.
    for i in range(n):
        for j in range(i + 1, n):
            if sim[i, j] >= sibling_threshold:
                union(i, j)

    # Group by root.
    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)

    # Cap oversized clusters: feature embeddings tend to share
    # boilerplate vocabulary, so even a strict threshold can produce
    # one mega-cluster that defeats the whole point of batching. For
    # any group exceeding ``max_cluster_size``, re-cluster its members
    # at a successively tighter threshold until every sub-cluster
    # fits. Stops at threshold 0.99 (effectively isolating each row)
    # so we never spin forever on a pathological input.
    capped_groups: list[list[int]] = []
    for member_indices in groups.values():
        if len(member_indices) <= max_cluster_size:
            capped_groups.append(member_indices)
            continue
        capped_groups.extend(
            _split_oversized_group(
                member_indices=member_indices,
                sim=sim,
                start_threshold=sibling_threshold,
                max_cluster_size=max_cluster_size,
            )
        )

    # EXISTING attachment — centroid of each group vs every existing
    # canonical's vector. Skip canonicals without an embedding; the
    # post-attach top-k filter handles the rest.
    existing_with_embedding = [
        (kid, title, np.asarray(emb, dtype=np.float32))
        for kid, title, emb in existing_canonicals
        if emb is not None
    ]
    existing_matrix: np.ndarray | None = None
    existing_norms: np.ndarray | None = None
    if existing_with_embedding:
        existing_matrix = np.stack([vec for _, _, vec in existing_with_embedding])
        en = np.linalg.norm(existing_matrix, axis=1, keepdims=True)
        en[en == 0] = 1.0
        existing_norms = existing_matrix / en

    clusters: list[MergeCluster] = []
    for member_indices in capped_groups:
        member_rows = [indexed[i][1] for i in member_indices]
        related: list[tuple[uuid.UUID, str]] = []
        if existing_norms is not None and existing_with_embedding:
            centroid = normalised[member_indices].mean(axis=0)
            cn = np.linalg.norm(centroid)
            if cn > 0:
                centroid = centroid / cn
            scores = existing_norms @ centroid
            ranked = np.argsort(-scores)
            for rank_idx in ranked[:max_existing_per_cluster]:
                if scores[rank_idx] < existing_threshold:
                    break
                kid, title, _ = existing_with_embedding[int(rank_idx)]
                related.append((kid, title))
        clusters.append(MergeCluster(synth_rows=member_rows, related_existing=related))

    # Append no-embedding rows as standalone singletons (no related
    # existing; they'll be promoted directly or processed alone).
    clusters.extend(MergeCluster(synth_rows=[r]) for r in no_embedding)

    # Stable order: by smallest member id.
    clusters.sort(key=lambda c: min(r.id for r in c.synth_rows))

    logger.info(
        "feature_merge_clusters_built",
        total_synth_rows=len(synth_rows),
        cluster_count=len(clusters),
        singleton_solo_count=sum(1 for c in clusters if c.is_singleton_with_no_existing_match),
        existing_canonicals=len(existing_canonicals),
        max_cluster_size=max(
            (len(c.synth_rows) for c in clusters),
            default=0,
        ),
    )
    return clusters


def _split_oversized_group(
    *,
    member_indices: list[int],
    sim: np.ndarray,
    start_threshold: float,
    max_cluster_size: int,
    threshold_step: float = 0.03,
    threshold_ceiling: float = 0.99,
) -> list[list[int]]:
    """Re-cluster an oversized group at progressively tighter thresholds.

    Walks the members at a higher threshold via union-find on the
    pre-computed ``sim`` matrix. Recurses on sub-groups that are still
    too big until every output group fits ``max_cluster_size`` or the
    threshold reaches ``threshold_ceiling`` (at which point each row
    becomes its own singleton — guaranteed termination).
    """
    threshold = round(start_threshold + threshold_step, 4)
    if threshold >= threshold_ceiling:
        # Hard floor — isolate every row. Prevents infinite recursion
        # when many rows have essentially identical embeddings.
        return [[idx] for idx in member_indices]

    parent = {idx: idx for idx in member_indices}

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    n = len(member_indices)
    for ai in range(n):
        for bi in range(ai + 1, n):
            i_a = member_indices[ai]
            i_b = member_indices[bi]
            if sim[i_a, i_b] >= threshold:
                union(i_a, i_b)

    sub_groups: dict[int, list[int]] = {}
    for idx in member_indices:
        sub_groups.setdefault(find(idx), []).append(idx)

    out: list[list[int]] = []
    for sub in sub_groups.values():
        if len(sub) <= max_cluster_size:
            out.append(sub)
        else:
            # Still oversized — recurse with tighter threshold.
            out.extend(
                _split_oversized_group(
                    member_indices=sub,
                    sim=sim,
                    start_threshold=threshold,
                    max_cluster_size=max_cluster_size,
                    threshold_step=threshold_step,
                    threshold_ceiling=threshold_ceiling,
                )
            )
    return out
