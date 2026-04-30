# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Cosine prefilter — reduces N-way candidate fan-out before the Claude call.

In production this becomes a SQL query on the pgvector index
(``query_repo_features``). Here we read embeddings into Python and
score in-process — fine for sandbox sizes (<100 features per repo).
"""

from dataclasses import dataclass

from experiments.cross_layer_merge.prompts.verify_pair import FeatureView
from experiments.cross_layer_merge.schema import XLMSynthesizedFeature

PREFILTER_LIMIT = 5


@dataclass
class SourceWithSynth:
    """Bundle a synth row with its FeatureView projection.

    The verifier uses ``synth`` for FK references when applying merges
    and ``view`` for prompt rendering.
    """

    synth: XLMSynthesizedFeature
    view: FeatureView


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Plain cosine — small vectors so no numpy needed in the sandbox."""
    dot: float = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a: float = sum(x * x for x in a) ** 0.5
    norm_b: float = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def prefilter_candidates(
    source: SourceWithSynth, candidates: list[SourceWithSynth]
) -> list[SourceWithSynth]:
    """Top-K by cosine if embeddings present; otherwise return everything (capped).

    When embeddings are missing (e.g. seed JSON omitted them), fall
    back to a no-op cap so the verifier still runs end-to-end on
    title/description alone.
    """
    src_vec = source.synth.embedding
    if src_vec is None or not candidates or candidates[0].synth.embedding is None:
        return candidates[:PREFILTER_LIMIT]

    scored: list[tuple[float, SourceWithSynth]] = []
    for c in candidates:
        if c.synth.embedding is None:
            continue
        score = cosine_similarity(src_vec, c.synth.embedding)
        scored.append((score, c))
    scored.sort(key=lambda t: t[0], reverse=True)
    top = scored[:PREFILTER_LIMIT]
    for sim, cand in top:
        cand.view.similarity = sim
    return [c for _, c in top]
