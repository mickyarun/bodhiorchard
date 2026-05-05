# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Per-org threshold calibration for the cluster-merge phase.

Hardcoded thresholds (0.85 same-layer / 0.80 cross-layer) were tuned
on the Atoa Payments dataset. A different org with different
vocabulary, repo count, or feature granularity will have a different
similarity distribution — what's "tight" for Atoa may be too loose
for a multi-product platform and too tight for a tiny startup.

This module computes thresholds **from the data** the merge phase is
about to operate on. Approach:

1. Walk every (a, b) pair of synth rows with embeddings.
2. Bucket the pairwise cosine into ``same_layer_sims`` or
   ``cross_layer_sims`` based on the repo's classified layer.
3. Pick the threshold for each bucket as the Pth percentile — the
   intuition is "retain only the top X% of pairs as cluster
   candidates, regardless of what the absolute cosine value is".
   Defaults: 99.5th percentile same-layer, 99.0th cross-layer
   (looser cross-layer because vocabulary drift across frontend ↔
   backend is real and predictable).

Trade-offs:
- Lower percentile (e.g. p98) → more pairs cluster, more Claude
  calls, larger clusters, higher risk of mega-cluster.
- Higher percentile (e.g. p99.9) → fewer pairs, more singletons,
  cross-layer twins miss.

The Pth-percentile rule scales naturally across orgs: a payments
org and a SaaS org will have completely different cosine
distributions, but "the top 0.5% of within-layer pairs" remains a
stable concept.
"""

from __future__ import annotations

import statistics
import uuid
from dataclasses import dataclass

import structlog

from experiments.cross_layer_merge.pair.prefilter import cosine_similarity
from experiments.cross_layer_merge.schema import (
    XLMSynthesizedFeature,
    XLMTrackedRepo,
)

log = structlog.get_logger(__name__)


# Same-layer stays tight: within-layer pairs share vocabulary, so a high
# percentile is a real signal. Cross-layer is loosened (p97 vs p99) — the
# embedding model compresses UI vocabulary ("Login & Authentication") and
# API vocabulary ("JWT Sessions") into different latent regions, so the
# cosine gate is the wrong place to filter cross-layer twins. Cast a wider
# net here; Claude (the second-stage reranker) is the actual judge.
# Pattern: standard retrieve-then-rerank — generous recall, accurate prune.
DEFAULT_SAME_LAYER_PERCENTILE = 99.5
DEFAULT_CROSS_LAYER_PERCENTILE = 97.0

# Hard floors so a degenerate org (every pair near 0.5) doesn't end up
# with an absurdly low calibrated threshold. Same-layer floor stays at
# 0.70; cross-layer floor drops to 0.60 because UI ↔ API embedding gap
# routinely sits in the 0.60-0.70 band even for true twins.
MIN_SAME_LAYER_THRESHOLD = 0.70
MIN_CROSS_LAYER_THRESHOLD = 0.60

# Hard ceilings so we never exceed the "obviously similar" boundary —
# even if every pair in the org sits above 0.95 (toy dataset),
# capping at 0.95 keeps the comparison meaningful.
MAX_SAME_LAYER_THRESHOLD = 0.95
MAX_CROSS_LAYER_THRESHOLD = 0.95


@dataclass(frozen=True)
class CalibratedThresholds:
    """Result of calibrating against an org's actual cosine distribution."""

    same_layer: float
    cross_layer: float
    same_pair_count: int
    cross_pair_count: int
    same_above_threshold: int
    cross_above_threshold: int
    same_percentile: float
    cross_percentile: float


def calibrate_thresholds(
    *,
    synth_rows: list[XLMSynthesizedFeature],
    repos: list[XLMTrackedRepo],
    same_layer_percentile: float = DEFAULT_SAME_LAYER_PERCENTILE,
    cross_layer_percentile: float = DEFAULT_CROSS_LAYER_PERCENTILE,
) -> CalibratedThresholds:
    """Pick per-layer thresholds based on actual pairwise cosines.

    Returns the chosen thresholds clamped to [MIN, MAX] hard bounds so
    a degenerate input (no pairs, or every pair near 1.0) still yields
    sensible thresholds the clusterer can use.
    """
    layer_lookup: dict[uuid.UUID, str] = {
        r.id: (r.repo_layer.value if r.repo_layer else "unknown") for r in repos
    }
    same: list[float] = []
    cross: list[float] = []
    rows_with_emb = [r for r in synth_rows if r.embedding is not None]
    for i, a in enumerate(rows_with_emb):
        for b in rows_with_emb[i + 1 :]:
            sim = cosine_similarity(list(a.embedding), list(b.embedding))
            if layer_lookup.get(a.repo_id) == layer_lookup.get(b.repo_id):
                same.append(sim)
            else:
                cross.append(sim)

    same_threshold = _percentile_or_default(same, same_layer_percentile, MIN_SAME_LAYER_THRESHOLD)
    cross_threshold = _percentile_or_default(
        cross, cross_layer_percentile, MIN_CROSS_LAYER_THRESHOLD
    )
    same_threshold = min(max(same_threshold, MIN_SAME_LAYER_THRESHOLD), MAX_SAME_LAYER_THRESHOLD)
    cross_threshold = min(
        max(cross_threshold, MIN_CROSS_LAYER_THRESHOLD), MAX_CROSS_LAYER_THRESHOLD
    )

    result = CalibratedThresholds(
        same_layer=round(same_threshold, 4),
        cross_layer=round(cross_threshold, 4),
        same_pair_count=len(same),
        cross_pair_count=len(cross),
        same_above_threshold=sum(1 for x in same if x >= same_threshold),
        cross_above_threshold=sum(1 for x in cross if x >= cross_threshold),
        same_percentile=same_layer_percentile,
        cross_percentile=cross_layer_percentile,
    )
    log.info(
        "calibrate.done",
        same_layer=result.same_layer,
        cross_layer=result.cross_layer,
        same_pairs=result.same_pair_count,
        cross_pairs=result.cross_pair_count,
        same_above=result.same_above_threshold,
        cross_above=result.cross_above_threshold,
    )
    return result


def _percentile_or_default(values: list[float], pct: float, fallback: float) -> float:
    """Pth percentile of ``values`` (statistics.quantiles uses 1..N indexing).

    Falls back to ``fallback`` when ``values`` is too small to compute
    a stable percentile (≤ 1 entry, or all identical).
    """
    if len(values) < 2:
        return fallback
    # statistics.quantiles requires n>=2; pct 99.5 maps to index 994 of 999.
    n = 1000
    quantiles = statistics.quantiles(values, n=n)
    idx = max(0, min(n - 2, int(round(pct / 100 * n)) - 1))
    return quantiles[idx]
