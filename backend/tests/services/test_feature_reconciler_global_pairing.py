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

"""Global-resolution pairing in :func:`_resolve_pairings`.

Pins the prod regression where the per-write greedy matcher let an
earlier write claim a candidate via a borderline-quality edge, leaving
the later write that would have been the clean pair to insert-as-new
while the displaced candidate was swept inactive. The PR-merge synthesis
on the payments repo on 2026-06-01 showed this pattern repeatedly —
"Cache Service" ↔ "Cache Service" (cosine 0.857), "Vendor Rollout Flags"
↔ "Vendor Rollout Flags" (0.845), and ~10 more title-identical or
near-identical pairs.

The resolver now sorts edges within each tier by score descending so the
strongest pair claims first.
"""

from __future__ import annotations

import math
import uuid

from app.services.feature_reconciler import (
    CONTAINMENT_THRESHOLD,
    COSINE_THRESHOLD,
    JACCARD_THRESHOLD,
    FeatureWrite,
    ReconcilerCandidate,
    _resolve_pairings,
)


def _candidate(
    *,
    signature: str,
    files: list[str] | None = None,
    embedding: list[float] | None = None,
    is_active: bool = True,
    title: str | None = None,
) -> ReconcilerCandidate:
    return ReconcilerCandidate(
        feature_id=uuid.uuid4(),
        feature_title=title or f"feat-{signature}",
        cluster_signature=signature,
        code_locations={"frontend": list(files)} if files else None,
        embedding=embedding,
        is_active=is_active,
        tags=[],
    )


def _write(
    *,
    signature: str,
    files: list[str] | None = None,
    embedding: list[float] | None = None,
    title: str = "w",
) -> FeatureWrite:
    return FeatureWrite(
        feature_title=title,
        description="desc",
        capabilities={},
        cluster_names=["c"],
        cluster_signature=signature,
        tags=[],
        embedding=embedding,
        code_locations={"frontend": list(files)} if files else None,
    )


def _unit(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec))
    return [x / norm for x in vec]


def _resolve(
    writes: list[FeatureWrite],
    candidates: list[ReconcilerCandidate],
) -> list[tuple[ReconcilerCandidate | None, str, float]]:
    return _resolve_pairings(
        writes,
        candidates,
        {c.cluster_signature: c for c in candidates},
        jaccard_threshold=JACCARD_THRESHOLD,
        cosine_threshold=COSINE_THRESHOLD,
        containment_threshold=CONTAINMENT_THRESHOLD,
    )


def test_strongest_jaccard_pair_wins_when_two_writes_compete_for_one_candidate() -> None:
    """Two writes overlap the same candidate via Jaccard; the higher-scoring
    write must claim the candidate, leaving the weaker one to fall through.

    Old greedy: whichever write came first in ``synthesised`` won. New
    resolver: scoring decides, regardless of input order.
    """
    cand = _candidate(signature="sig-c", files=["a", "b", "c", "d"])
    # weaker_write: jaccard = 2 / 5 = 0.4  → BELOW threshold, no jaccard edge
    weaker_write = _write(signature="sig-weak", files=["a", "b", "x"])
    # strong_write: jaccard = 4 / 4 = 1.0 → above threshold
    strong_write = _write(signature="sig-strong", files=["a", "b", "c", "d"])

    # Order #1: strong first
    pairings_a = _resolve([strong_write, weaker_write], [cand])
    assert pairings_a[0][0] is cand
    assert pairings_a[0][1] == "jaccard"
    assert pairings_a[1] == (None, "insert", 0.0)

    # Order #2: weak first — old greedy would have stolen cand for the
    # weak write (its only edge being below threshold anyway). New
    # resolver: same outcome because score order beats input order.
    pairings_b = _resolve([weaker_write, strong_write], [cand])
    assert pairings_b[1][0] is cand
    assert pairings_b[1][1] == "jaccard"
    assert pairings_b[0] == (None, "insert", 0.0)


def test_cosine_pair_assigned_by_score_descending_not_input_order() -> None:
    """Reproduces the prod failure: two writes both have cosine ≥ threshold
    against the same candidate; the higher-cosine write wins.

    Old greedy: the write that walked the candidate list first claimed it.
    New resolver: 0.99 wins over 0.86 regardless of input order, so the
    legitimate twin no longer gets orphaned + soft-deleted.
    """
    cand_emb = _unit([1.0, 0.0, 0.0])
    cand = _candidate(signature="sig-c", embedding=cand_emb, title="Cache Service")
    # weak: cosine ≈ 0.86 (slightly above threshold)
    weak_emb = _unit([0.86, 0.51, 0.0])
    weaker_write = _write(signature="sig-other", embedding=weak_emb, title="Caching Layer")
    # strong: cosine ≈ 0.99
    strong_emb = _unit([0.99, 0.141, 0.0])
    strong_write = _write(signature="sig-cache", embedding=strong_emb, title="Cache Service")

    # weak first in input order. Old greedy would have given cand to weak;
    # new resolver gives cand to strong because 0.99 > 0.86.
    pairings = _resolve([weaker_write, strong_write], [cand])

    weaker_match, weaker_via, _ = pairings[0]
    strong_match, strong_via, strong_score = pairings[1]

    assert strong_match is cand
    assert strong_via == "cosine"
    assert strong_score > 0.95
    # The weaker write does NOT steal the candidate anymore.
    assert weaker_match is None
    assert weaker_via == "insert"


def test_signature_tier_still_pre_empts_lower_tiers() -> None:
    """Exact ``cluster_signature`` match remains non-negotiable even when a
    different write would score higher against the same candidate via a
    later tier. Signature is tier 1 and runs before global score sort.
    """
    cand_emb = _unit([1.0, 0.0])
    cand = _candidate(signature="sig-EXACT", files=["a", "b"], embedding=cand_emb)

    # signature_write hits the signature lookup but has weak content.
    signature_write = _write(signature="sig-EXACT", files=["zzz"])
    # cosine_write would otherwise win on score, but signature already
    # claimed cand.
    cosine_write = _write(signature="sig-other", embedding=_unit([0.99, 0.141]))

    pairings = _resolve([cosine_write, signature_write], [cand])

    # cosine_write does not get the candidate — signature_write does.
    assert pairings[0] == (None, "insert", 0.0)
    sig_match, sig_via, sig_score = pairings[1]
    assert sig_match is cand
    assert sig_via == "signature"
    assert sig_score == 1.0


def test_unmatched_writes_become_inserts_unmatched_candidates_left_for_sweep() -> None:
    """Sanity: writes with no qualifying tier edge get ``insert`` and the
    candidate they would have orphaned is left for the caller's sweep.
    """
    cand = _candidate(signature="sig-orphan", files=["lonely.vue"])
    # Embedding far from candidate's (none here) and no file overlap.
    write = _write(signature="sig-new", files=["unrelated.vue"])

    pairings = _resolve([write], [cand])

    assert pairings == [(None, "insert", 0.0)]


def test_strong_pair_does_not_block_weaker_pair_from_finding_its_match() -> None:
    """Two writes, two candidates. The strongest edge claims first; the
    second write must still get to claim its best remaining option.

    Pins the worry that score-descending sort might let one write
    swallow a candidate the other write also needed.

    Edges (Jaccard tier):
      A ↔ X = 10/11 ≈ 0.91  (strongest)
      B ↔ Y = 10/11 ≈ 0.91  (independent of A↔X — different candidate)
    """
    cand_x = _candidate(signature="sig-x", files=[f"x{i}" for i in range(10)], title="X")
    cand_y = _candidate(signature="sig-y", files=[f"y{i}" for i in range(10)], title="Y")
    write_a = _write(
        signature="sig-a",
        files=[f"x{i}" for i in range(10)] + ["a-extra"],
        title="A→X",
    )
    write_b = _write(
        signature="sig-b",
        files=[f"y{i}" for i in range(10)] + ["b-extra"],
        title="B→Y",
    )

    pairings = _resolve([write_a, write_b], [cand_x, cand_y])

    assert pairings[0][0] is cand_x
    assert pairings[0][1] == "jaccard"
    assert pairings[1][0] is cand_y
    assert pairings[1][1] == "jaccard"


def test_jaccard_tier_still_beats_cosine_for_same_pair() -> None:
    """A pair that qualifies in both Jaccard and cosine tiers must match
    via Jaccard, regardless of which tier scores higher numerically.

    Without this invariant the resolver could silently change semantics
    for tier-overlap pairs — e.g. an exact file-overlap pair gets
    re-tagged ``cosine`` if its embedding similarity ran higher than
    its Jaccard, breaking the ``match_via`` audit-log contract.
    """
    files = ["a.ts", "b.ts", "c.ts"]
    cand = _candidate(
        signature="sig-c",
        files=files,
        embedding=_unit([1.0, 0.0, 0.0]),
    )
    write = _write(
        signature="sig-w",
        files=files,  # Jaccard = 1.0
        embedding=_unit([0.99, 0.141, 0.0]),  # cosine ≈ 0.99
    )

    pairings = _resolve([write], [cand])
    match, via, score = pairings[0]

    assert match is cand
    assert via == "jaccard"
    assert score == 1.0
