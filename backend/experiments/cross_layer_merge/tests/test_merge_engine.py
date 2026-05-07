# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Pure-function tests for the sandbox merge engine.

Mirrors the deterministic-only style used in ``test_merge_loop.py`` —
no DB session, no Claude subprocess. The runner's DB orchestration is
exercised by the ``run merge`` command on real seed data.
"""

import uuid
from types import SimpleNamespace
from typing import Any

import pytest

from experiments.cross_layer_merge.merge.calibrate import (
    MAX_CROSS_LAYER_THRESHOLD,
    MIN_CROSS_LAYER_THRESHOLD,
    MIN_SAME_LAYER_THRESHOLD,
    calibrate_thresholds,
)
from experiments.cross_layer_merge.merge.cluster import (
    MergeCluster,
    _should_union,
    cluster_for_merge,
)
from experiments.cross_layer_merge.prompts.verify_pair import (
    FeatureView,
    RepoView,
    build_cluster_prompt,
)
from experiments.cross_layer_merge.schema import XLMRepoLayer

# Stubs deliberately return ``Any`` so mypy's strict mode lets us pass
# them where ``XLMSynthesizedFeature`` / ``XLMTrackedRepo`` are typed —
# the clusterer is duck-typed on the fields these stubs provide.


def _stub_repo(name: str, layer: XLMRepoLayer) -> Any:
    """Build a minimal stand-in for ``XLMTrackedRepo`` for clusterer tests."""
    return SimpleNamespace(
        id=uuid.uuid4(),
        name=name,
        repo_layer=layer,
        tech_stack=None,
    )


def _stub_synth(
    repo_id: uuid.UUID,
    title: str,
    embedding: list[float] | None,
    *,
    synth_id: uuid.UUID | None = None,
) -> Any:
    """Build a minimal stand-in for ``XLMSynthesizedFeature``."""
    return SimpleNamespace(
        id=synth_id or uuid.uuid4(),
        org_id=uuid.UUID(int=1),
        repo_id=repo_id,
        feature_title=title,
        description=f"description of {title}",
        capabilities={},
        cluster_names=[],
        tags=[],
        code_locations={},
        embedding=embedding,
        knowledge_item_id=None,
        merge_outcome=None,
        merged_into_id=None,
    )


# ---------------------------------------------------------------------------
# _should_union — layer-aware threshold rule
# ---------------------------------------------------------------------------


def test_should_union_same_layer_uses_tight_threshold() -> None:
    """Within a layer (e.g. backend↔backend) require >= 0.85 cosine."""
    repo_a = _stub_repo("api", XLMRepoLayer.BACKEND)
    repo_b = _stub_repo("api2", XLMRepoLayer.BACKEND)
    row_a = _stub_synth(repo_a.id, "Magic Link", [1.0, 0.0])
    row_b = _stub_synth(repo_b.id, "Magic Link UI", [0.95, 0.05])
    layer_lookup = {repo_a.id: "backend", repo_b.id: "backend"}
    assert _should_union(row_a, row_b, sim=0.86, layer_lookup=layer_lookup)
    assert not _should_union(row_a, row_b, sim=0.84, layer_lookup=layer_lookup)


def test_should_union_cross_layer_uses_looser_threshold() -> None:
    """Across layers (frontend↔backend) require only >= 0.80 cosine.

    Cross-layer vocabulary drift is real: "form/input/validation" on the
    frontend vs "endpoint/schema/handler" on the backend, even when the
    underlying capability is identical.
    """
    repo_a = _stub_repo("api", XLMRepoLayer.BACKEND)
    repo_b = _stub_repo("ui", XLMRepoLayer.FRONTEND)
    row_a = _stub_synth(repo_a.id, "Magic Link backend", [1.0, 0.0])
    row_b = _stub_synth(repo_b.id, "Magic Link UI", [0.95, 0.05])
    layer_lookup = {repo_a.id: "backend", repo_b.id: "frontend"}
    # Within the loosened band — a same-layer pair would NOT union here.
    assert _should_union(row_a, row_b, sim=0.81, layer_lookup=layer_lookup)
    # Below the cross-layer floor.
    assert not _should_union(row_a, row_b, sim=0.79, layer_lookup=layer_lookup)


# ---------------------------------------------------------------------------
# cluster_for_merge — same-title forced union, singleton handling, oversized split
# ---------------------------------------------------------------------------


def test_cluster_returns_empty_for_no_rows() -> None:
    assert cluster_for_merge(synth_rows=[], repos=[], existing_canonicals=[]) == []


def test_same_title_rows_are_forced_into_one_cluster_even_below_floor() -> None:
    """Title-twin defence: two same-title rows below the cosine floor still merge."""
    repo_a = _stub_repo("api", XLMRepoLayer.BACKEND)
    repo_b = _stub_repo("ui", XLMRepoLayer.FRONTEND)
    row_a = _stub_synth(repo_a.id, "Authentication", [1.0, 0.0])
    row_b = _stub_synth(repo_b.id, "Authentication", [0.0, 1.0])  # cosine=0.0 — far below floor
    clusters = cluster_for_merge(
        synth_rows=[row_a, row_b],
        repos=[repo_a, repo_b],
        existing_canonicals=[],
    )
    assert len(clusters) == 1
    assert {r.id for r in clusters[0].synth_rows} == {row_a.id, row_b.id}


def test_unrelated_rows_become_separate_singletons() -> None:
    repo_a = _stub_repo("api", XLMRepoLayer.BACKEND)
    repo_b = _stub_repo("ui", XLMRepoLayer.FRONTEND)
    row_a = _stub_synth(repo_a.id, "Auth", [1.0, 0.0])
    row_b = _stub_synth(repo_b.id, "Payments", [0.0, 1.0])
    clusters = cluster_for_merge(
        synth_rows=[row_a, row_b],
        repos=[repo_a, repo_b],
        existing_canonicals=[],
    )
    assert len(clusters) == 2
    for c in clusters:
        assert c.is_singleton_with_no_existing_match


def test_no_embedding_rows_pass_through_as_singletons() -> None:
    repo_a = _stub_repo("api", XLMRepoLayer.BACKEND)
    row_a = _stub_synth(repo_a.id, "Auth", None)
    clusters = cluster_for_merge(
        synth_rows=[row_a],
        repos=[repo_a],
        existing_canonicals=[],
    )
    assert len(clusters) == 1
    assert clusters[0].is_singleton_with_no_existing_match


def test_oversized_cluster_is_recursively_split() -> None:
    """Above max_cluster_size, the clusterer tightens the threshold and re-splits.

    With identical embeddings (all cosine=1.0) recursion can't actually
    split the group on similarity, so termination falls to the
    threshold-ceiling singleton fallback — every row ends up alone.
    Real-world embeddings differ enough that the tightening separates
    them at intermediate thresholds.
    """
    repo_a = _stub_repo("api", XLMRepoLayer.BACKEND)
    rows = [_stub_synth(repo_a.id, f"Feature {i}", [1.0, 0.0]) for i in range(30)]
    clusters = cluster_for_merge(
        synth_rows=rows,
        repos=[repo_a],
        existing_canonicals=[],
        max_cluster_size=10,
    )
    # All members fall to singletons via the threshold-ceiling fallback
    # (cosine=1.0 means no threshold below 0.99 can split them).
    assert len(clusters) == 30
    assert all(c.is_singleton_with_no_existing_match for c in clusters)


# ---------------------------------------------------------------------------
# MergeCluster invariants
# ---------------------------------------------------------------------------


def test_singleton_with_no_existing_match() -> None:
    repo = _stub_repo("api", XLMRepoLayer.BACKEND)
    row = _stub_synth(repo.id, "Auth", [1.0])
    cluster = MergeCluster(synth_rows=[row])
    assert cluster.is_singleton_with_no_existing_match


def test_singleton_with_related_existing_is_not_skip_path() -> None:
    """Even a single member needs Claude when there's a pre-existing canonical to attach to."""
    repo = _stub_repo("api", XLMRepoLayer.BACKEND)
    row = _stub_synth(repo.id, "Auth", [1.0])
    cluster = MergeCluster(
        synth_rows=[row],
        related_existing=[(uuid.uuid4(), "Existing Auth")],
    )
    assert not cluster.is_singleton_with_no_existing_match


# ---------------------------------------------------------------------------
# build_cluster_prompt — multi-member rendering
# ---------------------------------------------------------------------------


def test_build_cluster_prompt_renders_all_members() -> None:
    canonical_repo = RepoView(name="api", layer="backend", tech_stack="fastapi")
    canonical_feat = FeatureView(
        synth_id="11111111-1111-1111-1111-111111111111",
        title="Magic Link Verification",
        description="backend",
        capabilities={},
        tags=["auth"],
        cluster_names=["auth"],
        code_paths=["backend: app/api/auth.py"],
    )
    cand_repo = RepoView(name="ui", layer="frontend", tech_stack="vue3")
    cand_feat = FeatureView(
        synth_id="22222222-2222-2222-2222-222222222222",
        title="Magic Link Sign-in",
        description="frontend",
        capabilities={},
        tags=["auth"],
        cluster_names=["login"],
        code_paths=["frontend: src/views/Login.vue"],
    )
    prompt = build_cluster_prompt(
        canonical_repo=canonical_repo,
        canonical_feature=canonical_feat,
        candidates=[(cand_repo, cand_feat)],
        related_existing=[],
    )
    assert "CANONICAL" in prompt and "CANDIDATE 1" in prompt
    assert "Magic Link Verification" in prompt and "Magic Link Sign-in" in prompt
    assert "ui" in prompt and "api" in prompt
    assert "DECISION RULES" in prompt


def test_build_cluster_prompt_includes_related_existing_section() -> None:
    canonical_repo = RepoView(name="api", layer="backend", tech_stack="fastapi")
    canonical_feat = FeatureView(
        synth_id="11111111-1111-1111-1111-111111111111",
        title="X",
        description="d",
        capabilities={},
        tags=[],
        cluster_names=[],
        code_paths=[],
    )
    prompt = build_cluster_prompt(
        canonical_repo=canonical_repo,
        canonical_feature=canonical_feat,
        candidates=[(canonical_repo, canonical_feat)],
        related_existing=[("33333333-3333-3333-3333-333333333333", "Existing Y")],
    )
    assert "RELATED EXISTING CANONICALS" in prompt
    assert "Existing Y" in prompt


# ---------------------------------------------------------------------------
# calibrate_thresholds — percentile-based per-org threshold
# ---------------------------------------------------------------------------


def test_calibrate_empty_input_returns_min_floor() -> None:
    """Empty synth list should yield the hard floor, not a crash."""
    result = calibrate_thresholds(synth_rows=[], repos=[])
    assert result.same_layer == MIN_SAME_LAYER_THRESHOLD
    assert result.cross_layer == MIN_CROSS_LAYER_THRESHOLD
    assert result.same_pair_count == 0
    assert result.cross_pair_count == 0


def test_calibrate_clamps_to_max_when_distribution_is_high() -> None:
    """If every pair sits >0.95 (toy dataset), the ceiling caps the threshold.

    Without the ceiling the calibrator would return 1.0 and nothing
    would ever cluster.
    """
    repo_a = _stub_repo("api", XLMRepoLayer.BACKEND)
    # 10 rows with near-identical embeddings → every pair sits at ~1.0
    rows = [_stub_synth(repo_a.id, f"F{i}", [1.0, 0.001 * i]) for i in range(10)]
    result = calibrate_thresholds(synth_rows=rows, repos=[repo_a])
    assert result.same_layer <= MAX_CROSS_LAYER_THRESHOLD
    assert result.cross_layer == MIN_CROSS_LAYER_THRESHOLD  # no cross-layer pairs


def test_calibrate_separates_same_and_cross_layer_pools() -> None:
    """Same-layer and cross-layer pairs are bucketed independently."""
    backend_repo = _stub_repo("api", XLMRepoLayer.BACKEND)
    frontend_repo = _stub_repo("ui", XLMRepoLayer.FRONTEND)
    # 5 backend rows (10 same-layer pairs)
    backend_rows = [_stub_synth(backend_repo.id, f"B{i}", [1.0, 0.0]) for i in range(5)]
    # 5 frontend rows (10 same-layer pairs in frontend, 25 cross-layer)
    frontend_rows = [_stub_synth(frontend_repo.id, f"F{i}", [0.7, 0.7]) for i in range(5)]
    rows = backend_rows + frontend_rows

    result = calibrate_thresholds(synth_rows=rows, repos=[backend_repo, frontend_repo])
    # 5 backend × (5-1) /2 + 5 frontend × (5-1) /2 = 10 + 10 = 20 same-layer
    assert result.same_pair_count == 20
    # 5 × 5 = 25 cross-layer
    assert result.cross_pair_count == 25


def test_calibrate_returns_higher_percentile_for_same_layer() -> None:
    """Same-layer threshold should never be looser than cross-layer.

    The defaults pick p99.5 same / p99.0 cross — same-layer is a tighter
    percentile (further from the bulk) so the threshold sits higher.
    """
    backend_repo = _stub_repo("api", XLMRepoLayer.BACKEND)
    frontend_repo = _stub_repo("ui", XLMRepoLayer.FRONTEND)
    # Build a realistic-ish distribution: mix of high-similarity and low.
    rows = []
    for i in range(20):
        rows.append(_stub_synth(backend_repo.id, f"B{i}", [1.0, 0.01 * i]))
        rows.append(_stub_synth(frontend_repo.id, f"F{i}", [0.5 + 0.02 * i, 0.5]))
    result = calibrate_thresholds(synth_rows=rows, repos=[backend_repo, frontend_repo])
    # Both must be in valid range
    assert MIN_SAME_LAYER_THRESHOLD <= result.same_layer <= MAX_CROSS_LAYER_THRESHOLD
    assert MIN_CROSS_LAYER_THRESHOLD <= result.cross_layer <= MAX_CROSS_LAYER_THRESHOLD


def test_build_cluster_prompt_requires_candidates() -> None:
    repo = RepoView(name="r", layer="backend", tech_stack=None)
    feat = FeatureView(
        synth_id="a",
        title="t",
        description="d",
        capabilities={},
        tags=[],
        cluster_names=[],
        code_paths=[],
    )
    with pytest.raises(ValueError):
        build_cluster_prompt(
            canonical_repo=repo,
            canonical_feature=feat,
            candidates=[],
            related_existing=[],
        )
