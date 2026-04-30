# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Pure-function tests for the cross-layer merge sandbox.

These tests target deterministic logic (allowed-pair predicate, cosine
similarity, prompt assembly, response parsing). DB-touching paths are
exercised by the sandbox CLI itself — we don't replicate them here
because the sandbox is the test bench.
"""

import json
import uuid
from types import SimpleNamespace

import pytest

from experiments.cross_layer_merge.pair.claude_client import parse_verdict
from experiments.cross_layer_merge.pair.planner import _is_allowed, _pair_kind
from experiments.cross_layer_merge.pair.prefilter import (
    SourceWithSynth,
    cosine_similarity,
    prefilter_candidates,
)
from experiments.cross_layer_merge.prompts.verify_pair import (
    FeatureView,
    RepoView,
    build_prompt,
)
from experiments.cross_layer_merge.schema import XLMRepoLayer

# ---------------------------------------------------------------------------
# Pair planner predicates
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "a,b,expected",
    [
        (XLMRepoLayer.FRONTEND, XLMRepoLayer.BACKEND, True),
        (XLMRepoLayer.BACKEND, XLMRepoLayer.FRONTEND, True),  # order-insensitive
        (XLMRepoLayer.FRONTEND, XLMRepoLayer.PROCESSOR, True),
        (XLMRepoLayer.BACKEND, XLMRepoLayer.PROCESSOR, True),
        (XLMRepoLayer.BACKEND, XLMRepoLayer.BACKEND, True),  # microservices
        (XLMRepoLayer.FRONTEND, XLMRepoLayer.FRONTEND, False),  # excluded
        (XLMRepoLayer.PROCESSOR, XLMRepoLayer.PROCESSOR, False),
        (XLMRepoLayer.FRONTEND, XLMRepoLayer.DB, False),
    ],
)
def test_is_allowed(a: XLMRepoLayer, b: XLMRepoLayer, expected: bool) -> None:
    assert _is_allowed(a, b) is expected


def test_pair_kind_is_order_insensitive() -> None:
    fwd = _pair_kind(XLMRepoLayer.FRONTEND, XLMRepoLayer.BACKEND)
    rev = _pair_kind(XLMRepoLayer.BACKEND, XLMRepoLayer.FRONTEND)
    assert fwd == rev == "backend×frontend"


# ---------------------------------------------------------------------------
# Cosine similarity + prefilter
# ---------------------------------------------------------------------------


def test_cosine_similarity_extremes() -> None:
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)
    assert cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0  # zero-norm guard


def _stub_source(synth_id: str, embedding: list[float] | None) -> SourceWithSynth:
    """Tiny stub for prefilter unit tests — no real ORM row."""
    return SourceWithSynth(
        synth=SimpleNamespace(id=uuid.UUID(synth_id), embedding=embedding),  # type: ignore[arg-type]
        view=FeatureView(
            synth_id=synth_id,
            title="t",
            description="d",
            capabilities={},
            tags=[],
            cluster_names=[],
            code_paths=[],
        ),
    )


def test_prefilter_caps_when_embeddings_missing() -> None:
    src = _stub_source("00000000-0000-0000-0000-000000000001", None)
    cands = [_stub_source(f"00000000-0000-0000-0000-{i:012x}", None) for i in range(2, 12)]
    out = prefilter_candidates(src, cands)
    assert len(out) == 5  # PREFILTER_LIMIT


def test_prefilter_ranks_by_cosine_when_embeddings_present() -> None:
    src = _stub_source("00000000-0000-0000-0000-000000000001", [1.0, 0.0])
    cands = [
        _stub_source("00000000-0000-0000-0000-000000000002", [1.0, 0.0]),  # sim=1.0
        _stub_source("00000000-0000-0000-0000-000000000003", [0.5, 0.5]),  # sim≈0.707
        _stub_source("00000000-0000-0000-0000-000000000004", [0.0, 1.0]),  # sim=0.0
    ]
    out = prefilter_candidates(src, cands)
    assert out[0].view.synth_id.endswith("002")
    assert out[0].view.similarity == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------


def test_build_prompt_renders_all_sections() -> None:
    repo_a = RepoView(name="ATOACore", layer="backend", tech_stack="fastapi")
    repo_b = RepoView(name="MerchantDashboard", layer="frontend", tech_stack="vue3")
    source = FeatureView(
        synth_id="src-1",
        title="Authentication",
        description="Backend auth handler",
        capabilities={"verify_token": True},
        tags=["auth"],
        cluster_names=["auth"],
        code_paths=["backend: app/api/auth.py:1-50"],
    )
    candidate = FeatureView(
        synth_id="cand-1",
        title="Login",
        description="Frontend login form",
        capabilities={"submit_email": True},
        tags=["auth"],
        cluster_names=["login"],
        code_paths=["frontend: src/views/Login.vue:1-100"],
    )
    prompt = build_prompt(
        source_repo=repo_a,
        source_feature=source,
        target_repo=repo_b,
        candidates=[candidate],
    )
    assert "ATOACore" in prompt and "MerchantDashboard" in prompt
    assert "Authentication" in prompt and "Login" in prompt
    assert "DECISION RULES" in prompt
    assert "RESPOND WITH ONLY A SINGLE JSON OBJECT" in prompt


def test_build_prompt_requires_candidates() -> None:
    src_repo = RepoView(name="A", layer="backend", tech_stack=None)
    src = FeatureView(
        synth_id="a",
        title="t",
        description="d",
        capabilities={},
        tags=[],
        cluster_names=[],
        code_paths=[],
    )
    with pytest.raises(ValueError):
        build_prompt(
            source_repo=src_repo,
            source_feature=src,
            target_repo=src_repo,
            candidates=[],
        )


# ---------------------------------------------------------------------------
# Response parser
# ---------------------------------------------------------------------------


def test_parse_verdict_merge() -> None:
    payload = json.dumps(
        {
            "action": "merge",
            "canonical_synth_id": "11111111-1111-1111-1111-111111111111",
            "absorb_synth_ids": ["22222222-2222-2222-2222-222222222222"],
            "rationale": "same magic-link flow",
        }
    )
    verdict = parse_verdict("Some prose...\n" + payload + "\nmore prose")
    assert verdict["action"] == "merge"
    assert len(verdict["absorb_synth_ids"]) == 1


def test_parse_verdict_no_match() -> None:
    verdict = parse_verdict('{"action": "no_match", "rationale": "different goals"}')
    assert verdict["action"] == "no_match"


def test_parse_verdict_rejects_unknown_action() -> None:
    with pytest.raises(ValueError):
        parse_verdict('{"action": "split", "rationale": "..."}')


def test_parse_verdict_rejects_merge_missing_fields() -> None:
    with pytest.raises(ValueError):
        parse_verdict('{"action": "merge", "rationale": "incomplete"}')


def test_parse_verdict_no_json_block() -> None:
    with pytest.raises(ValueError):
        parse_verdict("just prose with no json")
