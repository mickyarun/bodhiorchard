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

"""Dispatcher cap on ``pr_merge_update``.

When the PR-merge feature reconcile job identifies *N* affected
clusters:

* ``N == 0`` → today's no-op path (no narrow job, no full scan).
* ``0 < N <= NARROW_CAP`` → ``_enqueue_narrow_synthesis`` enqueues a
  ``JOB_PR_NARROW_SYNTHESIS`` job with the affected cluster ids on
  the payload; the dispatcher job is marked COMPLETED.
* ``N > NARROW_CAP`` → fall back to today's ``_trigger_repo_scan``
  (full-repo scan path); narrow job is NOT enqueued.

Tests target the dispatcher branch points only — the narrow handler's
own behaviour is covered by ``test_pr_narrow_synthesis``.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from app.services.scan import pr_merge_update as mod


@pytest.fixture
def captured() -> dict[str, Any]:
    return {"narrow_payload": None, "scan_triggered": False, "job_state": None}


@pytest.fixture
def _patched(monkeypatch: pytest.MonkeyPatch, captured: dict[str, Any]) -> None:
    """Stub every IO entry-point the dispatcher reaches, plus the two
    sinks (narrow + scan).

    Per-test overrides of ``_find_affected_clusters`` are still required
    — that helper is the *behaviour under test*. The other DB helpers
    (``_load_repo_and_org``, ``_fetch_changed_paths``) get the same
    no-op stub so a future test author can't accidentally hit Postgres
    or the GitHub API.
    """

    def _fake_create_job(job_type: str, *, payload: dict[str, Any], user_id: Any) -> str:
        captured["narrow_payload"] = (job_type, payload)
        return "narrow-job-id"

    async def _fake_trigger_scan(_job_id: str, **kw: Any) -> None:
        captured["scan_triggered"] = True
        captured["scan_reason"] = kw.get("reason")

    def _fake_update_job(_job_id: str, **kw: Any) -> None:
        if "state" in kw:
            captured["job_state"] = kw["state"]

    async def _fake_no_paths(*_a: Any, **_kw: Any) -> set[str]:
        return set()

    monkeypatch.setattr(mod, "create_job", _fake_create_job)
    monkeypatch.setattr(mod, "_trigger_repo_scan", _fake_trigger_scan)
    monkeypatch.setattr(mod, "update_job", _fake_update_job)
    monkeypatch.setattr(mod, "_load_repo_and_org", _fake_repo_and_org)
    monkeypatch.setattr(mod, "_fetch_changed_paths", _fake_no_paths)


def test_enqueue_narrow_synthesis_payload_shape(
    _patched: None, captured: dict[str, Any]
) -> None:
    org_id = uuid.uuid4()
    repo_id = uuid.uuid4()
    mod._enqueue_narrow_synthesis(
        "dispatcher-job-id",
        org_id=org_id,
        repo_id=repo_id,
        pr_number=42,
        base_sha="basesha",
        head_sha="headsha",
        full_name="owner/example",
        affected={"c10", "c2", "c11"},
    )
    job_type, payload = captured["narrow_payload"]
    assert job_type == "pr_narrow_synthesis"
    assert payload["org_id"] == str(org_id)
    assert payload["repo_id"] == str(repo_id)
    assert payload["pr_number"] == 42
    assert payload["base_sha"] == "basesha"
    assert payload["head_sha"] == "headsha"
    assert payload["full_name"] == "owner/example"
    # Sorted for deterministic dedup keys downstream.
    assert payload["affected_cluster_ids"] == ["c10", "c11", "c2"]


async def test_dispatcher_picks_narrow_under_cap(
    monkeypatch: pytest.MonkeyPatch, _patched: None, captured: dict[str, Any]
) -> None:
    """``len(affected) <= NARROW_CAP`` → narrow path, no full scan."""
    affected = {f"c{i}" for i in range(mod.NARROW_CAP)}  # exactly == cap

    async def _resolved(*_a: Any, **_kw: Any) -> set[str] | None:
        return affected

    monkeypatch.setattr(mod, "_find_affected_clusters", _resolved)

    payload = {
        "org_id": str(uuid.uuid4()),
        "repo_id": str(uuid.uuid4()),
        "pr_number": 7,
        "base_sha": "b",
        "head_sha": "h",
        "full_name": "owner/r",
    }
    await mod.handle_pr_merge_update("dispatcher-job-id", payload)
    assert captured["scan_triggered"] is False
    assert captured["narrow_payload"] is not None
    assert len(captured["narrow_payload"][1]["affected_cluster_ids"]) == mod.NARROW_CAP


async def test_dispatcher_falls_back_to_full_scan_above_cap(
    monkeypatch: pytest.MonkeyPatch, _patched: None, captured: dict[str, Any]
) -> None:
    """``len(affected) > NARROW_CAP`` → full ``start_scan`` path, no narrow."""
    affected = {f"c{i}" for i in range(mod.NARROW_CAP + 1)}

    async def _resolved(*_a: Any, **_kw: Any) -> set[str] | None:
        return affected

    monkeypatch.setattr(mod, "_find_affected_clusters", _resolved)

    payload = {
        "org_id": str(uuid.uuid4()),
        "repo_id": str(uuid.uuid4()),
        "pr_number": 7,
        "base_sha": "b",
        "head_sha": "h",
        "full_name": "owner/r",
    }
    await mod.handle_pr_merge_update("dispatcher-job-id", payload)
    assert captured["scan_triggered"] is True
    assert captured["narrow_payload"] is None
    assert "above narrow cap" in captured["scan_reason"]


async def test_dispatcher_noop_when_no_clusters_affected(
    monkeypatch: pytest.MonkeyPatch, _patched: None, captured: dict[str, Any]
) -> None:
    """``len(affected) == 0`` → neither path runs; job completes cleanly."""

    async def _empty(*_a: Any, **_kw: Any) -> set[str] | None:
        return set()

    monkeypatch.setattr(mod, "_find_affected_clusters", _empty)

    payload = {
        "org_id": str(uuid.uuid4()),
        "repo_id": str(uuid.uuid4()),
        "pr_number": 7,
        "base_sha": "b",
        "head_sha": "h",
        "full_name": "owner/r",
    }
    await mod.handle_pr_merge_update("dispatcher-job-id", payload)
    assert captured["scan_triggered"] is False
    assert captured["narrow_payload"] is None


def test_enqueue_swallows_terminal_update_job_failure(
    monkeypatch: pytest.MonkeyPatch, captured: dict[str, Any]
) -> None:
    """Final ``update_job(COMPLETED)`` is best-effort.

    If the dispatcher row update fails AFTER the narrow child is
    already queued, raising would let the outer ``except`` flip the
    dispatcher to FAILED — telling GitHub's retry that nothing happened
    while the child is mid-flight. Swallowing the failure (with a
    warning log) keeps the contract: enqueue success = success.
    """

    def _fake_create_job(_jt: str, *, payload: dict[str, Any], user_id: Any) -> str:
        captured["narrow_payload"] = ("pr_narrow_synthesis", payload)
        return "narrow-job-id"

    def _flaky_update(_job_id: str, **_kw: Any) -> None:
        raise RuntimeError("simulated job-row update failure")

    monkeypatch.setattr(mod, "create_job", _fake_create_job)
    monkeypatch.setattr(mod, "update_job", _flaky_update)

    # Must NOT raise.
    mod._enqueue_narrow_synthesis(
        "dispatcher-job-id",
        org_id=uuid.uuid4(),
        repo_id=uuid.uuid4(),
        pr_number=1,
        base_sha="b",
        head_sha="h",
        full_name="o/r",
        affected={"c1"},
    )
    assert captured["narrow_payload"] is not None  # child WAS queued


async def _fake_repo_and_org(
    _db: Any, *, org_id: uuid.UUID, repo_id: uuid.UUID
) -> tuple[Any, Any]:
    """Minimal stand-in returning truthy repo + org for the handler's early gate."""

    class _Repo:
        github_repo_full_name = "owner/r"

    class _Org:
        id = org_id

    return _Repo(), _Org()
