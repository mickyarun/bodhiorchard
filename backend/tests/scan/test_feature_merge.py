# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Tests for the staging-then-merge feature flow.

Per-repo synthesis writes only to ``synthesized_features``; the merge
phase (B3) is the sole writer of canonical ``knowledge_items``. This
test file exercises the contract surfaces that the rewrite cares
about: ``apply_feature_merge_plan`` op shape, batch-level validation,
prompt rendering, and merge-model selection.

The phase orchestration (DB writes, transaction commits) is exercised
through end-to-end scan tests; running it here against the shared
session-scoped ``db_session`` fixture deadlocks on asyncpg's "another
operation in progress" — same constraint documented in
``test_scan_progress``.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

# ──────────────── apply_feature_merge_plan op shape ──────────────


def _op(action: str, **fields: object) -> dict[str, object]:
    """Build a minimal op dict for shape-validation tests.

    Either ``canonical_synth_id`` or ``canonical_knowledge_id`` should
    be supplied via ``fields``; passing both is a deliberate violation
    used by the XOR-validation test.
    """
    base: dict[str, object] = {"action": action}
    base.update(fields)
    return base


def test_op_shape_rejects_non_dict() -> None:
    """A non-dict op must surface a clear error string."""
    from app.mcp.handlers_feature_merge import _OpValidationError, _validate_op_shape

    with pytest.raises(_OpValidationError) as exc_info:
        _validate_op_shape(0, "not-a-dict")
    assert "must be an object" in exc_info.value.reason


def test_op_shape_rejects_unknown_action() -> None:
    """Action must be one of merge / link / create."""
    from app.mcp.handlers_feature_merge import _OpValidationError, _validate_op_shape

    bad = _op(
        "delete",
        canonical_synth_id="00000000-0000-0000-0000-000000000001",
    )
    with pytest.raises(_OpValidationError) as exc_info:
        _validate_op_shape(0, bad)
    assert "action must be one of" in exc_info.value.reason


def test_op_shape_rejects_neither_canonical_id() -> None:
    """One of canonical_synth_id or canonical_knowledge_id is required."""
    from app.mcp.handlers_feature_merge import _OpValidationError, _validate_op_shape

    with pytest.raises(_OpValidationError) as exc_info:
        _validate_op_shape(0, _op("create"))
    assert "exactly one of canonical_synth_id" in exc_info.value.reason


def test_op_shape_rejects_both_canonical_ids() -> None:
    """XOR: cannot set both canonical_synth_id and canonical_knowledge_id."""
    from app.mcp.handlers_feature_merge import _OpValidationError, _validate_op_shape

    bad = _op(
        "create",
        canonical_synth_id="00000000-0000-0000-0000-000000000001",
        canonical_knowledge_id="00000000-0000-0000-0000-000000000002",
    )
    with pytest.raises(_OpValidationError) as exc_info:
        _validate_op_shape(0, bad)
    assert "exactly one of canonical_synth_id" in exc_info.value.reason


def test_op_shape_rejects_invalid_canonical_synth_id() -> None:
    """canonical_synth_id must be a parseable UUID."""
    from app.mcp.handlers_feature_merge import _OpValidationError, _validate_op_shape

    with pytest.raises(_OpValidationError) as exc_info:
        _validate_op_shape(0, _op("merge", canonical_synth_id="not-a-uuid"))
    # Both ids parse to None, so the XOR check fires first; that's fine.
    assert exc_info.value.reason


def test_op_shape_rejects_canonical_synth_in_absorb_synth_ids() -> None:
    """A synth row cannot absorb itself."""
    from app.mcp.handlers_feature_merge import _OpValidationError, _validate_op_shape

    cid = "00000000-0000-0000-0000-000000000001"
    with pytest.raises(_OpValidationError) as exc_info:
        _validate_op_shape(
            0,
            _op("merge", canonical_synth_id=cid, absorb_synth_ids=[cid]),
        )
    assert "cannot appear in absorb_synth_ids" in exc_info.value.reason


def test_op_shape_rejects_canonical_ki_in_absorb_knowledge_ids() -> None:
    """A KI cannot absorb itself across the canonical/absorb split."""
    from app.mcp.handlers_feature_merge import _OpValidationError, _validate_op_shape

    cid = "00000000-0000-0000-0000-000000000001"
    with pytest.raises(_OpValidationError) as exc_info:
        _validate_op_shape(
            0,
            _op("merge", canonical_knowledge_id=cid, absorb_knowledge_ids=[cid]),
        )
    assert "cannot appear in absorb_knowledge_ids" in exc_info.value.reason


def test_op_shape_requires_absorb_for_merge_action() -> None:
    """``action=merge`` without ANY absorb id is rejected."""
    from app.mcp.handlers_feature_merge import _OpValidationError, _validate_op_shape

    with pytest.raises(_OpValidationError) as exc_info:
        _validate_op_shape(
            0,
            _op("merge", canonical_knowledge_id="00000000-0000-0000-0000-000000000001"),
        )
    assert "merge action requires" in exc_info.value.reason


def test_op_shape_accepts_link_with_only_repo_ids() -> None:
    """``action=link`` is the one valid path that omits absorb fields."""
    from app.mcp.handlers_feature_merge import _validate_op_shape

    cid = "00000000-0000-0000-0000-000000000001"
    rid = "00000000-0000-0000-0000-000000000002"
    parsed = _validate_op_shape(
        0,
        _op("link", canonical_synth_id=cid, repo_ids=[rid]),
    )
    assert parsed["action"] == "link"
    assert parsed["absorb_synth_ids"] == []
    assert parsed["absorb_knowledge_ids"] == []
    assert len(parsed["repo_ids"]) == 1


def test_op_shape_accepts_create_with_no_extras() -> None:
    """``action=create`` is purely declarative — canonical stays as is."""
    from app.mcp.handlers_feature_merge import _validate_op_shape

    cid = "00000000-0000-0000-0000-000000000001"
    parsed = _validate_op_shape(0, _op("create", canonical_synth_id=cid))
    assert parsed["action"] == "create"
    assert parsed["absorb_synth_ids"] == []
    assert parsed["absorb_knowledge_ids"] == []
    assert parsed["repo_ids"] == []


def test_op_shape_accepts_merge_with_existing_canonical() -> None:
    """NEW absorbed by EXISTING — the most common merge shape."""
    from app.mcp.handlers_feature_merge import _validate_op_shape

    parsed = _validate_op_shape(
        0,
        _op(
            "merge",
            canonical_knowledge_id="00000000-0000-0000-0000-000000000001",
            absorb_synth_ids=["00000000-0000-0000-0000-000000000002"],
        ),
    )
    assert parsed["canonical_knowledge_id"] is not None
    assert parsed["canonical_synth_id"] is None
    assert len(parsed["absorb_synth_ids"]) == 1


# ──────────────── apply_feature_merge_plan batch validation ──────────


class _FakeOrg:
    """Minimal stand-in for ``Organization`` at the handler boundary."""

    def __init__(self, oid: uuid.UUID) -> None:
        self.id = oid


@pytest.mark.asyncio(loop_scope="function")
async def test_batch_rejects_empty_ops_array() -> None:
    """The handler must refuse an empty / missing ops list early."""
    from app.mcp.handlers_feature_merge import handle_apply_feature_merge_plan

    org = _FakeOrg(uuid.uuid4())
    result = await handle_apply_feature_merge_plan(db=None, org=org, params={})  # type: ignore[arg-type]
    assert result == {"success": False, "error": "`ops` must be a non-empty array"}


@pytest.mark.asyncio(loop_scope="function")
async def test_batch_rejects_duplicate_canonical_synth_ids() -> None:
    """Two ops claiming the same canonical_synth_id produce conflicting audit rows."""
    from app.mcp.handlers_feature_merge import handle_apply_feature_merge_plan

    org = _FakeOrg(uuid.uuid4())
    cid = "00000000-0000-0000-0000-000000000001"
    aid_a = "00000000-0000-0000-0000-000000000002"
    aid_b = "00000000-0000-0000-0000-000000000003"
    params = {
        "ops": [
            _op("merge", canonical_synth_id=cid, absorb_synth_ids=[aid_a]),
            _op("merge", canonical_synth_id=cid, absorb_synth_ids=[aid_b]),
        ]
    }
    result = await handle_apply_feature_merge_plan(db=None, org=org, params=params)  # type: ignore[arg-type]
    assert result["success"] is False
    assert "duplicate canonical_synth_id" in result["error"]


@pytest.mark.asyncio(loop_scope="function")
async def test_batch_rejects_synth_appearing_as_canonical_and_absorb() -> None:
    """A synth row cannot be canonical in one op and absorb in another."""
    from app.mcp.handlers_feature_merge import handle_apply_feature_merge_plan

    org = _FakeOrg(uuid.uuid4())
    shared = "00000000-0000-0000-0000-000000000001"
    other_canonical = "00000000-0000-0000-0000-000000000002"
    other_absorb = "00000000-0000-0000-0000-000000000003"
    params = {
        "ops": [
            _op("merge", canonical_synth_id=shared, absorb_synth_ids=[other_absorb]),
            _op("merge", canonical_synth_id=other_canonical, absorb_synth_ids=[shared]),
        ]
    }
    result = await handle_apply_feature_merge_plan(db=None, org=org, params=params)  # type: ignore[arg-type]
    assert result["success"] is False
    assert "both canonical and absorb" in result["error"]


@pytest.mark.asyncio(loop_scope="function")
async def test_batch_propagates_op_validation_error() -> None:
    """Op-level shape errors surface the op index for the caller to debug."""
    from app.mcp.handlers_feature_merge import handle_apply_feature_merge_plan

    org = _FakeOrg(uuid.uuid4())
    params = {
        "ops": [
            _op(
                "merge",
                canonical_synth_id="00000000-0000-0000-0000-000000000001",
                absorb_synth_ids=["bad-uuid"],
            ),
        ]
    }
    result = await handle_apply_feature_merge_plan(db=None, org=org, params=params)  # type: ignore[arg-type]
    assert result["success"] is False
    assert "op[0]" in result["error"]
    assert "absorb_synth_ids must be a list of UUID strings" in result["error"]


# ──────────────── two-section prompt rendering ──────────────


def _new_feature_row(**overrides: Any) -> dict[str, Any]:
    """Build a NEW-feature dict keyed by ``synth_id``."""
    base: dict[str, Any] = {
        "synth_id": "11111111-1111-1111-1111-111111111111",
        "title": "Authentication",
        "repo_names": ["ATOACore", "ATOAPayment"],
        "tags": ["security", "identity"],
        "cluster_names": ["auth_handler_module"],
        "description": "Sign-in flow with OAuth + MFA.",
        "capabilities": ["sign in via OAuth", "reset password", "MFA challenge"],
        "code_locations": ["auth/oauth/google.ts", "auth/mfa/totp.ts"],
    }
    base.update(overrides)
    return base


def _existing_canonical_row(**overrides: Any) -> dict[str, Any]:
    """Build an EXISTING-canonical dict keyed by ``knowledge_id``."""
    base: dict[str, Any] = {
        "knowledge_id": "22222222-2222-2222-2222-222222222222",
        "title": "Payments",
        "repo_names": ["ATOAPayment"],
        "cluster_names": ["payment_service_module"],
        "summary": "Outbound payment execution against the OpenBanking VRP API.",
    }
    base.update(overrides)
    return base


def test_prompt_renders_two_section_when_existing_present() -> None:
    """The full template lists both EXISTING and NEW sections with id prefixes."""
    from app.scan.prompts import build_merge_prompt

    rendered = build_merge_prompt(
        new_features=[_new_feature_row()],
        existing_canonicals=[_existing_canonical_row()],
    )
    assert "## EXISTING canonicals" in rendered
    assert "## NEW features" in rendered
    # NEW rows carry the synth: prefix; EXISTING rows carry ki:.
    assert "[synth:11111111-1111-1111-1111-111111111111]" in rendered
    assert "[ki:22222222-2222-2222-2222-222222222222]" in rendered
    assert "description: Sign-in flow with OAuth + MFA." in rendered
    assert "summary: Outbound payment execution" in rendered


def test_prompt_collapses_to_single_section_when_existing_empty() -> None:
    """First-merge runs see NEW-only template, no EXISTING header."""
    from app.scan.prompts import build_merge_prompt

    rendered = build_merge_prompt(
        new_features=[_new_feature_row()],
        existing_canonicals=[],
    )
    assert "## EXISTING canonicals" not in rendered
    assert "## NEW features" in rendered
    assert "apply_feature_merge_plan" in rendered


def test_prompt_instructs_apply_feature_merge_plan_only() -> None:
    """The prompt must NOT mention the deleted ``merge_features`` tool."""
    from app.scan.prompts import build_merge_prompt

    rendered = build_merge_prompt(
        new_features=[_new_feature_row()],
        existing_canonicals=[_existing_canonical_row()],
    )
    assert "apply_feature_merge_plan" in rendered
    assert "merge_features" not in rendered


def test_prompt_includes_unlinked_repos_block_when_provided() -> None:
    """Repos with no features surface via the apply_feature_merge_plan repo_ids field."""
    from app.scan.prompts import build_merge_prompt

    rendered = build_merge_prompt(
        new_features=[_new_feature_row()],
        existing_canonicals=[],
        unlinked_repos=[{"name": "AtoaShortlinks", "files": ["src/redirect.ts"]}],
    )
    assert "Repos with no features yet" in rendered
    assert "AtoaShortlinks" in rendered
    assert "repo_ids" in rendered


def test_prompt_explains_canonical_id_xor_rule() -> None:
    """Claude must be told to set exactly one canonical id type per op."""
    from app.scan.prompts import build_merge_prompt

    rendered = build_merge_prompt(
        new_features=[_new_feature_row()],
        existing_canonicals=[_existing_canonical_row()],
    )
    assert "canonical_synth_id" in rendered
    assert "canonical_knowledge_id" in rendered
    assert "exactly one of" in rendered


# ──────────────── pick_merge_model boundary ────────────────


def test_pick_merge_model_below_threshold_uses_default() -> None:
    """At or below merge_sonnet_quality_budget, default model wins."""
    from app.services.scan.phase_impls.feature_merge import pick_merge_model

    chosen = pick_merge_model(2999, default_model="sonnet", large_model="opus")
    assert chosen == "sonnet"


def test_pick_merge_model_at_threshold_uses_default() -> None:
    """Exactly at the threshold (3000) is still in the default band."""
    from app.services.scan.phase_impls.feature_merge import pick_merge_model

    chosen = pick_merge_model(3000, default_model="sonnet", large_model="opus")
    assert chosen == "sonnet"


def test_pick_merge_model_above_threshold_escalates() -> None:
    """One above the threshold (3001) escalates to the large model."""
    from app.services.scan.phase_impls.feature_merge import pick_merge_model

    chosen = pick_merge_model(3001, default_model="sonnet", large_model="opus")
    assert chosen == "opus"


# ──────────────── get_merge_models per-org override ──────────────


def test_get_merge_models_returns_global_defaults_when_no_org_config() -> None:
    """``None`` config falls back to platform LLMConfig defaults."""
    from app.config import settings
    from app.services.org_settings import get_merge_models

    default, large = get_merge_models(None)
    assert default == settings.llm.merge_model_default
    assert large == settings.llm.merge_model_large


def test_get_merge_models_honours_valid_per_org_override() -> None:
    """A valid allowlisted override wins over the platform default."""
    from app.services.org_settings import get_merge_models

    org_config = {
        "llm": {
            "merge_model_default": "claude-opus-4-7",
            "merge_model_large": "claude-sonnet-4-6",
        }
    }
    default, large = get_merge_models(org_config)
    assert default == "claude-opus-4-7"
    assert large == "claude-sonnet-4-6"


def test_get_merge_models_falls_back_when_override_outside_allowlist() -> None:
    """Misspelled override silently falls back to platform default."""
    from app.config import settings
    from app.services.org_settings import get_merge_models

    org_config = {
        "llm": {
            "merge_model_default": "claude-haiku-99",  # not in allowlist
            "merge_model_large": "claude-opus-4-7",
        }
    }
    default, large = get_merge_models(org_config)
    assert default == settings.llm.merge_model_default
    assert large == "claude-opus-4-7"


# ──────────────── repository surface ──────────────


@pytest.mark.asyncio(loop_scope="function")
async def test_synth_repo_exposes_new_methods() -> None:
    """Sanity check: the new merge-flow methods exist on the repository."""
    import asyncio

    from app.repositories.synthesized_feature import SynthesizedFeatureRepository

    for method_name in (
        "list_unmerged_for_scan",
        "list_unmerged_org_wide",
        "back_fill_knowledge_item_id",
    ):
        method = getattr(SynthesizedFeatureRepository, method_name)
        assert asyncio.iscoroutinefunction(method)


def test_apply_feature_merge_plan_schema_matches_handler() -> None:
    """Round-trip: a schema-conformant op passes ``_validate_op_shape``.

    Regression guard for the schema drift that left ``canonical_id`` /
    ``absorb_ids`` advertised to Claude while the handler had moved to
    ``canonical_synth_id`` etc. — every MCP call was rejected and the
    merge silently produced 0 ops applied.
    """
    from app.mcp.handlers_feature_merge import _validate_op_shape
    from app.mcp.server import MCP_TOOLS

    tool = next((t for t in MCP_TOOLS if t.name == "apply_feature_merge_plan"), None)
    assert tool is not None, "apply_feature_merge_plan must be registered"

    op_schema = tool.input_schema["properties"]["ops"]["items"]
    nested_keys = set(op_schema["properties"].keys())
    # The new four-id shape — these must all be present in the schema.
    expected = {
        "action",
        "canonical_synth_id",
        "canonical_knowledge_id",
        "absorb_synth_ids",
        "absorb_knowledge_ids",
        "repo_ids",
    }
    missing = expected - nested_keys
    assert not missing, f"schema missing post-refactor keys: {sorted(missing)}"

    # Build a schema-conformant op and check the validator accepts it.
    op = {
        "action": "merge",
        "canonical_knowledge_id": "00000000-0000-0000-0000-000000000001",
        "absorb_synth_ids": ["00000000-0000-0000-0000-000000000002"],
    }
    parsed = _validate_op_shape(0, op)
    assert parsed["canonical_knowledge_id"] is not None
    assert parsed["absorb_synth_ids"]


def test_cluster_for_merge_singleton_no_existing() -> None:
    """A solo synth row with no related EXISTING canonical → 1 singleton cluster."""
    from app.services.scan.phase_impls.feature_merge import cluster_for_merge

    class _StubSynth:
        def __init__(self, sid: uuid.UUID, embedding: list[float]) -> None:
            self.id = sid
            self.embedding = embedding
            self.feature_title = f"Feature: {sid}"

    row = _StubSynth(uuid.uuid4(), [1.0] + [0.0] * 383)
    clusters = cluster_for_merge(synth_rows=[row], existing_canonicals=[])  # type: ignore[arg-type]
    assert len(clusters) == 1
    assert clusters[0].is_singleton_with_no_existing_match


def test_cluster_for_merge_groups_similar_siblings() -> None:
    """Two synth rows with high cosine similarity collapse into one cluster."""
    from app.services.scan.phase_impls.feature_merge import cluster_for_merge

    class _StubSynth:
        def __init__(self, sid: uuid.UUID, embedding: list[float]) -> None:
            self.id = sid
            self.embedding = embedding
            self.feature_title = f"Feature: {sid}"

    # Both vectors point in nearly the same direction → cosine ≈ 1.
    row_a = _StubSynth(uuid.uuid4(), [1.0, 0.0] + [0.0] * 382)
    row_b = _StubSynth(uuid.uuid4(), [0.99, 0.01] + [0.0] * 382)
    # Third row points orthogonally → its own cluster.
    row_c = _StubSynth(uuid.uuid4(), [0.0, 0.0, 1.0] + [0.0] * 381)

    clusters = cluster_for_merge(  # type: ignore[arg-type]
        synth_rows=[row_a, row_b, row_c],
        existing_canonicals=[],
    )
    cluster_sizes = sorted(len(c.synth_rows) for c in clusters)
    assert cluster_sizes == [1, 2]
    pair_cluster = next(c for c in clusters if len(c.synth_rows) == 2)
    assert {r.id for r in pair_cluster.synth_rows} == {row_a.id, row_b.id}


def test_cluster_for_merge_groups_same_title_regardless_of_embedding() -> None:
    """Two synth rows with the same feature_title MUST cluster even if
    their embeddings drift below the cosine threshold. Without this
    guard, both would become singletons that try to promote to fresh
    KIs with the same title and trip the unique constraint.
    """
    from app.services.scan.phase_impls.feature_merge import cluster_for_merge

    class _StubSynth:
        def __init__(self, sid: uuid.UUID, title: str, embedding: list[float]) -> None:
            self.id = sid
            self.embedding = embedding
            self.feature_title = title

    # Same title, but vectors orthogonal (cosine = 0).
    a = _StubSynth(uuid.uuid4(), "Feature: Auth", [1.0, 0.0] + [0.0] * 382)
    b = _StubSynth(uuid.uuid4(), "Feature: Auth", [0.0, 1.0] + [0.0] * 382)
    # A third row with a unique title should stay separate.
    c = _StubSynth(uuid.uuid4(), "Feature: Billing", [0.0, 0.0, 1.0] + [0.0] * 381)

    clusters = cluster_for_merge(  # type: ignore[arg-type]
        synth_rows=[a, b, c],
        existing_canonicals=[],
    )
    cluster_sizes = sorted(len(c.synth_rows) for c in clusters)
    assert cluster_sizes == [1, 2]
    pair = next(c for c in clusters if len(c.synth_rows) == 2)
    assert {r.id for r in pair.synth_rows} == {a.id, b.id}


def test_cluster_for_merge_caps_oversized_clusters() -> None:
    """A near-identical set of N >> max_cluster_size synth rows must not
    collapse into one mega-cluster. The recursive splitter raises the
    threshold until each sub-cluster fits.
    """
    from app.services.scan.phase_impls.feature_merge import cluster_for_merge

    class _StubSynth:
        def __init__(self, sid: uuid.UUID, embedding: list[float]) -> None:
            self.id = sid
            self.embedding = embedding
            self.feature_title = f"Feature: {sid}"

    # 60 rows whose vectors are very close but not identical — at
    # threshold 0.85 they all union, at higher thresholds they split.
    rows = []
    for i in range(60):
        # Vary the second dim so cosine is high but not 1.0 between pairs.
        vec = [1.0, i / 1000.0] + [0.0] * 382
        rows.append(_StubSynth(uuid.uuid4(), vec))

    clusters = cluster_for_merge(  # type: ignore[arg-type]
        synth_rows=rows,
        existing_canonicals=[],
        max_cluster_size=25,
    )
    # Every cluster must respect the cap.
    assert all(len(c.synth_rows) <= 25 for c in clusters), [len(c.synth_rows) for c in clusters]
    # And every input row must be in exactly one output cluster.
    seen = {r.id for c in clusters for r in c.synth_rows}
    assert seen == {r.id for r in rows}


def test_cluster_for_merge_attaches_related_existing() -> None:
    """A cluster's centroid finds nearby EXISTING canonicals as related."""
    from app.services.scan.phase_impls.feature_merge import cluster_for_merge

    class _StubSynth:
        def __init__(self, sid: uuid.UUID, embedding: list[float]) -> None:
            self.id = sid
            self.embedding = embedding
            self.feature_title = f"Feature: {sid}"

    synth = _StubSynth(uuid.uuid4(), [1.0, 0.0] + [0.0] * 382)
    related_kid = uuid.uuid4()
    unrelated_kid = uuid.uuid4()

    clusters = cluster_for_merge(  # type: ignore[arg-type]
        synth_rows=[synth],
        existing_canonicals=[
            (related_kid, "Auth", [1.0, 0.0] + [0.0] * 382),  # cosine ≈ 1
            (unrelated_kid, "Billing", [0.0, 1.0] + [0.0] * 382),  # cosine = 0
        ],
    )
    assert len(clusters) == 1
    related_ids = [kid for kid, _ in clusters[0].related_existing]
    assert related_kid in related_ids
    assert unrelated_kid not in related_ids


def test_merge_runner_locks_tool_sandbox() -> None:
    """The merge phase must restrict Claude to ONLY the merge MCP tool.

    Without this, Claude has Bash / Read / ToolSearch available and tends
    to spend its turn budget exploring repo files instead of emitting
    the merge plan — burning the timeout on tool-use loops.
    """
    import inspect

    from app.services.scan.phase_impls import feature_merge

    src = inspect.getsource(feature_merge)
    assert 'allowed_tools=["mcp__bodhiorchard__apply_feature_merge_plan"]' in src, (
        "feature_merge.py must pass allowed_tools restricting the merge "
        "subprocess to the apply_feature_merge_plan MCP tool only"
    )
