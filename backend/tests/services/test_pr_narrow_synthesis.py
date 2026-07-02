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

"""Narrow synthesis function + prompt builder.

Two layers of coverage:

1. Pure-function tests for the narrow prompt builder and the
   ``row_to_community`` adapter — these have no IO and are easy to
   assert against.
2. Orchestration tests that monkeypatch the heavy dependencies (DB
   session, engine, reconciler) and assert that :func:`run_narrow_synthesis`:
   - scopes the reconcile pass via ``candidate_filter`` to the
     affected signatures only,
   - forwards the merge ``head_sha`` so soft-deletes are SHA-stamped,
   - drains the accumulator before reconciling,
   - returns the correct ``NarrowSynthesisOutcome``.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

import pytest

from app.schemas.scan import Community
from app.services.scan import pr_narrow_loader as loader_mod
from app.services.scan import pr_narrow_synthesis as handler_mod
from app.services.scan.pr_narrow_synthesis import (
    NarrowSynthesisOutcome,
    NarrowSynthesisParams,
)
from app.services.scan.synthesis.narrow_prompt import (
    ExistingFeatureContext,
    build_narrow_synthesis_prompt,
)

# --- Pure-function layer ----------------------------------------------------


def _existing(title: str = "Payments", **kw: Any) -> ExistingFeatureContext:
    defaults: dict[str, Any] = {
        "feature_title": title,
        "description": "Process payments.",
        "capabilities": ["charge", "refund"],
        "source": "scan",
        "source_ref": None,
        "feature_status": "implemented",
        "is_active": True,
        "deactivated_at_sha": None,
    }
    defaults.update(kw)
    return ExistingFeatureContext(**defaults)


def _community(signature: str, label: str = "payments") -> Community:
    return Community(
        community_id="c10",
        label=label,
        files=["src/payments/charge.py"],
        source_community_ids=["c10"],
        meta_community_id=signature,
        symbol_count=4,
    )


def _params(**overrides: Any) -> NarrowSynthesisParams:
    defaults: dict[str, Any] = {
        "org_id": uuid.uuid4(),
        "repo_id": uuid.uuid4(),
        "pr_number": 7,
        "base_sha": "basesha",
        "head_sha": "HEADSHA1",
        "full_name": "owner/example",
        "affected_signatures": ["sig-c10", "sig-c11"],
    }
    defaults.update(overrides)
    return NarrowSynthesisParams(**defaults)


def test_prompt_includes_existing_feature_for_known_signature() -> None:
    prompt = build_narrow_synthesis_prompt(
        repo_name="acme/api",
        communities=[_community("sig-a")],
        existing_by_signature={"sig-a": _existing("Payments")},
        repo_id="r-1",
    )
    assert "Payments" in prompt
    assert "Process payments." in prompt
    assert '"signature":"sig-a"' in prompt
    assert "repo_id" in prompt
    assert "r-1" in prompt


def test_prompt_omits_existing_block_for_net_new_cluster() -> None:
    prompt = build_narrow_synthesis_prompt(
        repo_name="acme/api",
        communities=[_community("sig-new")],
        existing_by_signature={},
    )
    assert '"signature":"sig-new"' in prompt
    assert '"existing_feature":' not in prompt


def test_prompt_carries_inactive_deactivation_sha_for_revive_context() -> None:
    prompt = build_narrow_synthesis_prompt(
        repo_name="acme/api",
        communities=[_community("sig-d")],
        existing_by_signature={
            "sig-d": _existing(
                "Old Feature",
                is_active=False,
                deactivated_at_sha="abc12345",
            )
        },
    )
    assert "abc12345" in prompt
    assert '"is_active":false' in prompt


def test_row_to_community_maps_signature_into_meta_community_id() -> None:
    @dataclass
    class _FakeRow:
        cluster_id: str
        label: str
        heuristic_label: str | None
        symbol_count: int
        cohesion: float | None
        files: list[str]
        signature: str

    row = _FakeRow(
        cluster_id="c42",
        label="payments",
        heuristic_label=None,
        symbol_count=10,
        cohesion=0.6,
        files=["a.py", "b.py"],
        signature="sig-c42",
    )
    community = loader_mod.row_to_community(row)  # type: ignore[arg-type]
    assert community.community_id == "c42"
    assert community.label == "payments"
    assert community.meta_community_id == "sig-c42"
    assert community.source_community_ids == ["c42"]


# --- Orchestration layer -----------------------------------------------------


@dataclass
class _CapturedReconcileCall:
    head_sha: str
    candidate_filter: Any
    synthesised: list[Any]


def _install_handler_fakes(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Stub every IO dependency of :func:`run_narrow_synthesis`."""
    captured: dict[str, Any] = {
        "reconcile": None,
        "drained": [],
        "engine_called": False,
        "reconcile_files": None,
    }

    class _FakeRepo:
        path = "/tmp/some/repo"
        github_repo_full_name = "owner/example"

    class _FakeRepoRepo:
        def __init__(self, *_a: Any, **_kw: Any) -> None:
            pass

        async def get_by_id(self, _id: uuid.UUID) -> Any:
            return _FakeRepo()

    async def _fake_load_scoped(
        _db: Any,
        *,
        org_id: uuid.UUID,
        repo_id: uuid.UUID,
        base_sha: str,
        head_sha: str,
        affected_signatures: list[str],
    ) -> tuple[list[Community], set[str], set[str]]:
        return (
            [_community("sig-a"), _community("sig-b")],
            {"sig-a", "sig-b"},
            {"a.py", "b.py"},
        )

    async def _fake_load_existing(
        _db: Any, *, org_id: uuid.UUID, repo_id: uuid.UUID, signatures: set[str]
    ) -> dict[str, ExistingFeatureContext]:
        return {"sig-a": _existing("Payments")}

    async def _fake_load_related(
        _db: Any,
        *,
        org_id: uuid.UUID,
        repo_id: uuid.UUID,
        affected_files: set[str],
        exclude_signatures: set[str],
    ) -> list[ExistingFeatureContext]:
        captured["related_call"] = {
            "affected_files": set(affected_files),
            "exclude_signatures": set(exclude_signatures),
        }
        return [_existing("Products Catalog")]

    async def _fake_run_claude(
        *, org_id: uuid.UUID, prompt: str, repo_path: str, repo_name: str
    ) -> dict[str, Any]:
        captured["engine_called"] = True
        captured["prompt_len"] = len(prompt)
        return {"success": True, "elapsed_ms": 1, "cost_usd": 0.0, "error": None}

    async def _fake_reconcile(
        *,
        org_id: uuid.UUID,
        repo_id: uuid.UUID,
        head_sha: str,
        signatures: set[str],
        affected_files: set[str],
    ) -> dict[str, int]:
        captured["reconcile"] = _CapturedReconcileCall(
            head_sha=head_sha,
            candidate_filter=signatures,
            synthesised=[],
        )
        captured["reconcile_files"] = affected_files
        return {"inserted": 2, "updated": 1, "revived": 0, "inactivated": 1}

    class _FakeSessionCtx:
        async def __aenter__(self) -> Any:
            return object()

        async def __aexit__(self, *_a: Any) -> None:
            return None

    # Cross-layer refresh helpers run after every reconcile. Their bodies
    # only catch (SQLAlchemyError, OSError) — programmer errors propagate.
    # The orchestration fakes here don't model the DB/Redis surface those
    # helpers reach, so we stub them out to no-ops; the helpers have their
    # own dedicated tests in test_narrow_cross_layer_refresh.py.
    async def _noop_refresh(*_a: Any, **_kw: Any) -> None:
        return None

    monkeypatch.setattr(handler_mod, "TrackedRepoRepository", _FakeRepoRepo)
    monkeypatch.setattr(handler_mod, "load_scoped_communities", _fake_load_scoped)
    monkeypatch.setattr(handler_mod, "load_existing_features_by_sig", _fake_load_existing)
    monkeypatch.setattr(handler_mod, "load_related_existing_features_by_files", _fake_load_related)
    monkeypatch.setattr(handler_mod, "_run_claude_narrow", _fake_run_claude)
    monkeypatch.setattr(handler_mod, "_reconcile_narrow", _fake_reconcile)
    monkeypatch.setattr(handler_mod, "_refresh_backend_links_post_reconcile", _noop_refresh)
    monkeypatch.setattr(handler_mod, "_refresh_cross_layer_from_backend_merge", _noop_refresh)
    monkeypatch.setattr(handler_mod, "AsyncSessionLocal", lambda: _FakeSessionCtx())

    return captured


async def test_run_narrow_synthesis_runs_engine_and_reconciles_scoped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _install_handler_fakes(monkeypatch)
    outcome = await handler_mod.run_narrow_synthesis(_params(head_sha="HEADSHA1"))

    assert captured["engine_called"] is True
    assert captured["reconcile"] is not None
    assert captured["reconcile"].head_sha == "HEADSHA1"
    assert captured["reconcile"].candidate_filter == {"sig-a", "sig-b"}
    assert outcome.succeeded
    assert outcome.branch == "synthesised"
    assert (outcome.inserted, outcome.updated, outcome.revived, outcome.inactivated) == (
        2,
        1,
        0,
        1,
    )


async def test_run_narrow_synthesis_returns_empty_branch_when_no_clusters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Affected ids may resolve to nothing if the cache evicted rows."""
    captured = _install_handler_fakes(monkeypatch)

    async def _empty_scoped(*_a: Any, **_kw: Any) -> tuple[list[Community], set[str], set[str]]:
        return [], set(), set()

    monkeypatch.setattr(handler_mod, "load_scoped_communities", _empty_scoped)
    outcome = await handler_mod.run_narrow_synthesis(_params())

    assert captured["engine_called"] is False
    assert outcome.branch == "empty"
    assert outcome.succeeded


async def test_run_narrow_synthesis_pure_deletion_skips_claude(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When affected clusters exist only at BASE_SHA:

    * communities is empty (nothing at head for Claude to read)
    * signatures is non-empty (carried from base_sha for the reconciler)

    Skip the Claude run entirely and go straight to reconcile.
    """
    captured = _install_handler_fakes(monkeypatch)

    async def _deletion_only_scoped(
        _db: Any,
        *,
        org_id: uuid.UUID,
        repo_id: uuid.UUID,
        base_sha: str,
        head_sha: str,
        affected_signatures: list[str],
    ) -> tuple[list[Community], set[str], set[str]]:
        return [], {"sig-removed-1"}, {"src/removed/file.py"}

    monkeypatch.setattr(handler_mod, "load_scoped_communities", _deletion_only_scoped)
    outcome = await handler_mod.run_narrow_synthesis(_params(head_sha="HEADDEL"))

    assert captured["engine_called"] is False, "Claude must not run on a pure-deletion PR"
    assert captured["reconcile"] is not None
    assert captured["reconcile"].head_sha == "HEADDEL"
    assert captured["reconcile"].candidate_filter == {"sig-removed-1"}
    assert outcome.branch == "deletion"


async def test_run_narrow_synthesis_failure_resets_accumulator_and_surfaces_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed Claude run must reset the accumulator and surface the
    error so the worker can flip the WebhookLog row to ``failed``.
    """
    _install_handler_fakes(monkeypatch)
    reset_calls: list[str] = []

    async def _failing_run(*_a: Any, **_kw: Any) -> dict[str, Any]:
        return {"success": False, "error": "boom", "elapsed_ms": 1, "cost_usd": None}

    monkeypatch.setattr(handler_mod, "_run_claude_narrow", _failing_run)
    monkeypatch.setattr(handler_mod, "reset_for_org", lambda org: reset_calls.append(org))

    params = _params()
    outcome = await handler_mod.run_narrow_synthesis(params)

    assert reset_calls == [str(params.org_id)]
    assert outcome.error == "boom"
    assert outcome.branch == "synthesised"
    assert not outcome.succeeded


# --- Phase 3: candidate_filter file-overlap fallback -------------------------


async def test_reconcile_filter_admits_features_via_file_overlap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When ``cluster_signature`` has drifted from current indexer output,
    the filter must still admit the feature into the reconciler pool
    via its ``code_locations`` overlap with the affected files.
    """
    from app.services.scan import pr_narrow_synthesis as ns

    captured_filter: dict[str, Any] = {}

    async def _spy_reconcile(*, candidate_filter: Any, **kw: Any) -> Any:
        captured_filter["fn"] = candidate_filter

        class _Summary:
            inserted = 0
            updated = 0
            revived = 0
            inactivated = 0
            match_log_rows: list[Any] = []

        return _Summary()

    class _NoopMatchLogRepo:
        def __init__(self, *_a: Any, **_kw: Any) -> None:
            pass

        async def bulk_insert(self, _rows: list[Any]) -> None:
            return None

    class _NoopSessionCtx:
        async def __aenter__(self) -> Any:
            class _Db:
                async def commit(self) -> None:
                    return None

            return _Db()

        async def __aexit__(self, *_a: Any) -> None:
            return None

    monkeypatch.setattr(ns, "reconcile_features_for_repo", _spy_reconcile)
    monkeypatch.setattr(ns, "FeatureMatchLogRepository", _NoopMatchLogRepo)
    monkeypatch.setattr(ns, "AsyncSessionLocal", lambda: _NoopSessionCtx())
    monkeypatch.setattr(ns, "drain", lambda *_a, **_kw: [])

    await ns._reconcile_narrow(
        org_id=uuid.uuid4(),
        repo_id=uuid.uuid4(),
        head_sha="HEAD",
        signatures={"current-sig"},
        affected_files={"reminders/scheduler.py", "reminders/__init__.py"},
    )
    fn = captured_filter["fn"]

    class _Cand:
        def __init__(self, sig: str, code_locations: dict[str, list[str]]) -> None:
            self.cluster_signature = sig
            self.code_locations = code_locations

    # 1. Signature match — primary path.
    assert fn(_Cand("current-sig", {})) is True

    # 2. Signature DRIFTED but code_locations files overlap — fallback admits.
    drifted = _Cand("stale-legacy-sig", {"backend": ["reminders/scheduler.py"]})
    assert fn(drifted) is True

    # 3. Drifted signature AND no file overlap → rejected.
    unrelated = _Cand("other-sig", {"backend": ["billing/router.py"]})
    assert fn(unrelated) is False

    # 4. Empty code_locations + sig miss → rejected.
    assert fn(_Cand("other-sig", {})) is False
    assert fn(_Cand("other-sig", {"frontend": None})) is False  # type: ignore[arg-type]


async def test_related_features_loader_called_with_excluded_signatures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The related-features loader fires with the PR's affected_files and
    excludes signatures already covered by ``load_existing_features_by_sig``
    so the prompt doesn't double-list the same broader feature."""
    captured = _install_handler_fakes(monkeypatch)
    await handler_mod.run_narrow_synthesis(_params())
    related_call = captured["related_call"]
    assert related_call["affected_files"] == {"a.py", "b.py"}
    # The fake _fake_load_existing returns ``{"sig-a": ...}`` only — so
    # exclude_signatures must be that exact set.
    assert related_call["exclude_signatures"] == {"sig-a"}


async def test_related_features_appear_in_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The Claude prompt must contain the related feature's title so the
    LLM can apply rule 6 (don't emit a duplicate for a narrow slice)."""
    _install_handler_fakes(monkeypatch)
    captured_prompts: list[str] = []

    async def _capture_prompt(*, prompt: str, **_kw: Any) -> dict[str, Any]:
        captured_prompts.append(prompt)
        return {"success": True, "elapsed_ms": 1, "cost_usd": 0.0, "error": None}

    monkeypatch.setattr(handler_mod, "_run_claude_narrow", _capture_prompt)
    await handler_mod.run_narrow_synthesis(_params())

    assert len(captured_prompts) == 1
    assert "Products Catalog" in captured_prompts[0]
    assert "related_features" in captured_prompts[0].lower() or "related" in captured_prompts[0]


async def test_reconcile_narrow_passes_signature_only_deactivate_filter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that the narrow reconcile path passes a stricter
    ``deactivate_filter`` than ``candidate_filter`` — signature-only.
    Without this, a feature admitted to the match pool via file overlap
    gets soft-deleted as collateral damage when nothing matches it.
    """
    from app.services.scan import pr_narrow_synthesis as ns

    captured_filters: dict[str, Any] = {}

    async def _spy_reconcile(
        *, candidate_filter: Any, deactivate_filter: Any = None, **kw: Any
    ) -> Any:
        captured_filters["candidate"] = candidate_filter
        captured_filters["deactivate"] = deactivate_filter

        class _Summary:
            inserted = 0
            updated = 0
            revived = 0
            inactivated = 0
            match_log_rows: list[Any] = []

        return _Summary()

    class _NoopMatchLogRepo:
        def __init__(self, *_a: Any, **_kw: Any) -> None:
            pass

        async def bulk_insert(self, _rows: list[Any]) -> None:
            return None

    class _NoopSessionCtx:
        async def __aenter__(self) -> Any:
            class _Db:
                async def commit(self) -> None:
                    return None

            return _Db()

        async def __aexit__(self, *_a: Any) -> None:
            return None

    monkeypatch.setattr(ns, "reconcile_features_for_repo", _spy_reconcile)
    monkeypatch.setattr(ns, "FeatureMatchLogRepository", _NoopMatchLogRepo)
    monkeypatch.setattr(ns, "AsyncSessionLocal", lambda: _NoopSessionCtx())
    monkeypatch.setattr(ns, "drain", lambda *_a, **_kw: [])

    await ns._reconcile_narrow(
        org_id=uuid.uuid4(),
        repo_id=uuid.uuid4(),
        head_sha="HEAD",
        signatures={"current-sig"},
        affected_files={"sidebar.vue"},
    )

    candidate_fn = captured_filters["candidate"]
    deactivate_fn = captured_filters["deactivate"]

    class _Cand:
        def __init__(self, sig: str, code_locations: dict[str, list[str]]) -> None:
            self.cluster_signature = sig
            self.code_locations = code_locations

    # File-overlap-admitted candidate — signature is NOT in affected set
    # but its code_locations overlap the affected files. The
    # candidate_filter must admit it (for matching), but the
    # deactivate_filter must REJECT it (to spare it from soft-delete).
    overlap_only = _Cand("legacy-sig", {"frontend": ["sidebar.vue", "other.vue"]})
    assert candidate_fn(overlap_only) is True
    assert deactivate_fn(overlap_only) is False

    # Signature-admitted candidate — both filters admit it.
    sig_admitted = _Cand("current-sig", {})
    assert candidate_fn(sig_admitted) is True
    assert deactivate_fn(sig_admitted) is True


def test_outcome_succeeded_helper() -> None:
    """``succeeded`` flips on ``error`` being non-None."""
    ok = NarrowSynthesisOutcome(branch="synthesised", inserted=1)
    assert ok.succeeded
    bad = NarrowSynthesisOutcome(branch="synthesised", error="oops")
    assert not bad.succeeded


async def test_run_claude_narrow_refreshes_token_before_spawning_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression guard for the wider stale-token fix.

    The narrow-synthesis subprocess runs ``git`` over the clone, so the
    installation token must be re-stamped before the engine spawns —
    otherwise a clone older than the 1-hour token TTL fails auth and
    the spawn aborts. Pins the ordering by recording the sequence of
    calls and asserting refresh precedes ``engine.run``.
    """
    call_sequence: list[str] = []

    async def fake_refresh(*, working_dir: str, org_id: uuid.UUID) -> bool:
        call_sequence.append(f"refresh:{working_dir}:{org_id}")
        return True

    class _FakeOutcome:
        success = True
        error: str | None = None
        elapsed_s = 0.0
        cost_usd = 0.0
        input_tokens = 0
        output_tokens = 0

    class _FakeEngine:
        async def run(self, request: Any) -> _FakeOutcome:
            call_sequence.append(f"engine:{request.working_dir}")
            return _FakeOutcome()

    # ``_run_claude_narrow`` loads the org to pick its provider; stub the
    # session + repo so this unit test never touches a DB (the engine that
    # would use the org is faked out anyway).
    @asynccontextmanager
    async def _fake_session() -> Any:
        yield object()

    class _FakeOrgRepo:
        def __init__(self, _db: Any) -> None: ...

        async def get_by_id(self, _entity_id: uuid.UUID) -> None:
            return None

    monkeypatch.setattr(handler_mod, "AsyncSessionLocal", _fake_session)
    monkeypatch.setattr(handler_mod, "OrganizationRepository", _FakeOrgRepo)
    monkeypatch.setattr(handler_mod, "refresh_origin_token_for_spawn", fake_refresh)
    monkeypatch.setattr(handler_mod, "AgentCliEngine", _FakeEngine)
    monkeypatch.setattr(handler_mod, "create_internal_mcp_token", lambda _org: "tok")
    # mcp_backend_url must be truthy or the function short-circuits before
    # reaching the refresh call we want to assert against.
    monkeypatch.setattr(
        handler_mod.app_settings, "mcp_backend_url", "http://mcp.test", raising=False
    )

    org_id = uuid.uuid4()
    out = await handler_mod._run_claude_narrow(
        org_id=org_id,
        prompt="...",
        repo_path="/clone/foo",
        repo_name="foo",
    )

    assert out["success"] is True
    assert call_sequence == [
        f"refresh:/clone/foo:{org_id}",
        "engine:/clone/foo",
    ], "refresh must run BEFORE engine.run — order pins the regression"
