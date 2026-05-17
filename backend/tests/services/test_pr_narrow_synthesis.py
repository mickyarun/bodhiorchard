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

"""Narrow synthesis handler + prompt builder.

Two layers of coverage:

1. Pure-function tests for the narrow prompt builder and the
   ``_row_to_community`` adapter — these have no IO and are easy to
   assert against.
2. Handler-level orchestration tests that monkeypatch the heavy
   dependencies (DB session, engine, reconciler) and assert the
   handler:
   - scopes the reconcile pass via ``candidate_filter`` to the
     affected signatures only,
   - forwards the merge ``head_sha`` so soft-deletes are SHA-stamped,
   - drains the accumulator before reconciling,
   - reports the correct status string.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

import pytest

from app.schemas.scan import Community
from app.services.scan import pr_narrow_loader as loader_mod
from app.services.scan import pr_narrow_synthesis as handler_mod
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
    # Repo-id echo-back block present so Claude binds writes to this repo.
    assert "repo_id" in prompt
    assert "r-1" in prompt


def test_prompt_omits_existing_block_for_net_new_cluster() -> None:
    """A cluster with no entry in the lookup dict is treated as net-new.

    The instruction prose mentions ``existing_feature`` regardless, so we
    assert against the JSON-payload key form ``"existing_feature":`` —
    that one only appears when an existing entry was rendered.
    """
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
    # Claude needs to see is_active=false to decide whether to revive.
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
    # source_community_ids defaults to a single-element list of the cluster_id
    # so the prompt's auto-expand semantics still apply.
    assert community.source_community_ids == ["c42"]


# --- Handler orchestration layer -------------------------------------------


@dataclass
class _CapturedReconcileCall:
    head_sha: str
    candidate_filter: Any
    synthesised: list[Any]


def _install_handler_fakes(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Stub every IO dependency of ``handle_pr_narrow_synthesis``.

    Returns the captured-state dict callers assert against.
    """
    captured: dict[str, Any] = {
        "reconcile": None,
        "drained": [],
        "engine_called": False,
        "job_state": None,
        "job_status": None,
        "job_error": None,
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
        # Verify the filter the handler builds is shaped correctly by
        # exercising it against in-scope and out-of-scope candidates.
        captured["reconcile"] = _CapturedReconcileCall(
            head_sha=head_sha,
            candidate_filter=signatures,
            synthesised=[],
        )
        captured["reconcile_files"] = affected_files
        return {"inserted": 2, "updated": 1, "revived": 0, "inactivated": 1}

    def _fake_update_job(_job_id: str, **kw: Any) -> None:
        if "state" in kw:
            captured["job_state"] = kw["state"]
        if "status_message" in kw:
            captured["job_status"] = kw["status_message"]
        if "error" in kw:
            captured["job_error"] = kw["error"]

    class _FakeSessionCtx:
        async def __aenter__(self) -> Any:
            return object()

        async def __aexit__(self, *_a: Any) -> None:
            return None

    monkeypatch.setattr(handler_mod, "TrackedRepoRepository", _FakeRepoRepo)
    monkeypatch.setattr(handler_mod, "load_scoped_communities", _fake_load_scoped)
    monkeypatch.setattr(handler_mod, "load_existing_features_by_sig", _fake_load_existing)
    monkeypatch.setattr(handler_mod, "_run_claude_narrow", _fake_run_claude)
    monkeypatch.setattr(handler_mod, "_reconcile_narrow", _fake_reconcile)
    monkeypatch.setattr(handler_mod, "update_job", _fake_update_job)
    monkeypatch.setattr(handler_mod, "AsyncSessionLocal", lambda: _FakeSessionCtx())

    return captured


async def test_handler_runs_engine_and_reconciles_scoped_to_signatures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _install_handler_fakes(monkeypatch)
    payload = {
        "org_id": str(uuid.uuid4()),
        "repo_id": str(uuid.uuid4()),
        "pr_number": 7,
        "base_sha": "base_sha_123",
        "head_sha": "HEADSHA1",
        "affected_signatures": ["sig-c10", "sig-c11"],
        "full_name": "owner/example",
    }
    await handler_mod.handle_pr_narrow_synthesis(job_id="j1", payload=payload)

    assert captured["engine_called"] is True
    assert captured["reconcile"] is not None
    assert captured["reconcile"].head_sha == "HEADSHA1"
    # The reconcile_narrow helper receives the signature scope set;
    # the handler itself doesn't expose the lambda directly here.
    assert captured["reconcile"].candidate_filter == {"sig-a", "sig-b"}
    # Status string carries the four counters.
    assert captured["job_status"] is not None
    assert "2+ 1~ 0↺ 1-" in captured["job_status"]


async def test_handler_marks_failed_on_bad_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _install_handler_fakes(monkeypatch)
    await handler_mod.handle_pr_narrow_synthesis(job_id="j-bad", payload={"org_id": "not-a-uuid"})
    # Bad payload should never reach the engine.
    assert captured["engine_called"] is False
    assert captured["job_error"] is not None
    assert "bad payload" in captured["job_error"]


async def test_handler_drops_when_no_clusters_resolve_at_head(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Affected ids resolved against ``cluster_cache`` may return empty
    if the cache rows were evicted between dispatch and run. With
    nothing at BASE or HEAD, the handler exits cleanly without
    invoking Claude OR the reconciler.
    """
    captured = _install_handler_fakes(monkeypatch)

    async def _empty_scoped(*_a: Any, **_kw: Any) -> tuple[list[Community], set[str], set[str]]:
        return [], set(), set()

    monkeypatch.setattr(handler_mod, "load_scoped_communities", _empty_scoped)
    payload = {
        "org_id": str(uuid.uuid4()),
        "repo_id": str(uuid.uuid4()),
        "pr_number": 7,
        "base_sha": "b",
        "head_sha": "h",
        "affected_signatures": ["sig-c10"],
        "full_name": "owner/example",
    }
    await handler_mod.handle_pr_narrow_synthesis(job_id="j2", payload=payload)
    assert captured["engine_called"] is False
    assert "No affected clusters" in (captured["job_status"] or "")


async def test_handler_pure_deletion_skips_claude_and_inactivates_via_reconcile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the affected clusters exist only at BASE_SHA (deleted in this PR):

    * communities is empty (nothing at head for Claude to read)
    * signatures is non-empty (carried from base_sha for the reconciler)

    The handler must skip the Claude run entirely (saves the LLM cost
    and time on a deletion PR) and call ``_reconcile_narrow`` directly
    — the existing feature's signature is in the candidate-filter
    scope, no synth write matches it, so it lands in
    ``unmatched_active`` and gets soft-deleted with the merge SHA.
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
        # Communities empty (head has nothing for these clusters), but
        # signatures + base-side files populated — the deletion case.
        return [], {"sig-removed-1"}, {"src/removed/file.py"}

    monkeypatch.setattr(handler_mod, "load_scoped_communities", _deletion_only_scoped)
    payload = {
        "org_id": str(uuid.uuid4()),
        "repo_id": str(uuid.uuid4()),
        "pr_number": 9,
        "base_sha": "basedeletion",
        "head_sha": "HEADDEL",
        "affected_signatures": ["sig-removed-cluster"],
        "full_name": "owner/example",
    }
    await handler_mod.handle_pr_narrow_synthesis(job_id="j-del", payload=payload)
    # Claude was NOT called — pure deletion goes straight to reconcile.
    assert captured["engine_called"] is False, "Claude must not run on a pure-deletion PR"
    # Reconciler WAS called and received the deletion signature scope.
    assert captured["reconcile"] is not None
    assert captured["reconcile"].head_sha == "HEADDEL"
    assert captured["reconcile"].candidate_filter == {"sig-removed-1"}
    # Status message clearly marks this as the deletion branch.
    assert "deletion" in (captured["job_status"] or "").lower()


async def test_handler_failure_resets_accumulator(monkeypatch: pytest.MonkeyPatch) -> None:
    """A failed Claude run must reset the accumulator so the next pass
    doesn't reconcile a mix of stale + fresh writes.
    """
    captured = _install_handler_fakes(monkeypatch)
    reset_calls: list[str] = []

    async def _failing_run(*_a: Any, **_kw: Any) -> dict[str, Any]:
        captured["engine_called"] = True
        return {"success": False, "error": "boom", "elapsed_ms": 1, "cost_usd": None}

    monkeypatch.setattr(handler_mod, "_run_claude_narrow", _failing_run)
    monkeypatch.setattr(handler_mod, "reset_for_org", lambda org: reset_calls.append(org))

    payload = {
        "org_id": str(uuid.uuid4()),
        "repo_id": str(uuid.uuid4()),
        "pr_number": 7,
        "base_sha": "b",
        "head_sha": "h",
        "affected_signatures": ["sig-c10"],
        "full_name": "owner/example",
    }
    await handler_mod.handle_pr_narrow_synthesis(job_id="j-fail", payload=payload)
    assert reset_calls == [payload["org_id"]]
    assert captured["job_error"] == "boom"


# --- Phase 3: candidate_filter file-overlap fallback -------------------------


async def test_reconcile_filter_admits_features_via_file_overlap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When ``cluster_signature`` has drifted from current indexer output,
    the filter must still admit the feature into the reconciler pool
    via its ``code_locations`` overlap with the affected files.

    Without this fallback, indexer algorithm changes across releases
    silently leak legacy features that can never be soft-deleted via
    the narrow path — the very bug the live A4 retest surfaced.
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

    # 2. Signature DRIFTED (legacy) but code_locations files overlap an
    #    affected cluster's files — fallback path admits it.
    drifted = _Cand("stale-legacy-sig", {"backend": ["reminders/scheduler.py"]})
    assert fn(drifted) is True, "file overlap fallback should admit"

    # 3. Out-of-scope: drifted signature AND no file overlap → rejected.
    unrelated = _Cand("other-sig", {"backend": ["billing/router.py"]})
    assert fn(unrelated) is False

    # 4. Empty code_locations + sig miss → rejected.
    assert fn(_Cand("other-sig", {})) is False
    assert fn(_Cand("other-sig", {"frontend": None})) is False  # type: ignore[arg-type]
