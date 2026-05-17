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
    return {
        "narrow_payload": None,
        "scan_triggered": False,
        "job_state": None,
        "backfill_calls": [],
    }


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

    async def _fake_index_and_cache(
        *, org_id: Any, repo_id: Any, repo_path: str, head_sha: str
    ) -> int:
        captured["backfill_calls"].append(
            {"repo_id": str(repo_id), "repo_path": repo_path, "head_sha": head_sha}
        )
        return 3  # arbitrary non-zero row count

    monkeypatch.setattr(mod, "create_job", _fake_create_job)
    monkeypatch.setattr(mod, "_trigger_repo_scan", _fake_trigger_scan)
    monkeypatch.setattr(mod, "update_job", _fake_update_job)
    monkeypatch.setattr(mod, "_load_repo_and_org", _fake_repo_and_org)
    monkeypatch.setattr(mod, "_fetch_changed_paths", _fake_no_paths)
    monkeypatch.setattr(mod, "index_and_cache", _fake_index_and_cache)


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

    async def _resolved(*_a: Any, **_kw: Any) -> tuple[set[str], str] | None:
        return (affected, "BASE")

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

    async def _resolved(*_a: Any, **_kw: Any) -> tuple[set[str], str] | None:
        return (affected, "BASE")

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

    async def _empty(*_a: Any, **_kw: Any) -> tuple[set[str], str] | None:
        return (set(), "BASE")

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
        path = "/tmp/repo"
        head_sha = "TRACKED_HEAD_SHA"

    class _Org:
        id = org_id

    return _Repo(), _Org()


# --- Phase 2: cluster_cache backfill pre-step --------------------------------


async def test_backfill_runs_before_find_affected_clusters(
    monkeypatch: pytest.MonkeyPatch, _patched: None, captured: dict[str, Any]
) -> None:
    """Dispatcher must call ``index_and_cache`` before ``_find_affected_clusters``.

    Without the backfill, ``head_rows`` is empty on every real-world PR
    merge → cache-miss → full scan. With the backfill, ``head_rows`` is
    populated and the existing algorithm runs as designed. We verify
    *ordering* via a call-log so a refactor that swaps the steps can't
    regress silently.
    """
    call_log: list[str] = []

    async def _logged_find(*_a: Any, **_kw: Any) -> tuple[set[str], str] | None:
        call_log.append("find_affected_clusters")
        return ({"c1"}, "BASE")

    async def _logged_backfill(**kw: Any) -> int:
        call_log.append("index_and_cache")
        captured["backfill_calls"].append(kw)
        return 5

    monkeypatch.setattr(mod, "_find_affected_clusters", _logged_find)
    monkeypatch.setattr(mod, "index_and_cache", _logged_backfill)

    payload = {
        "org_id": str(uuid.uuid4()),
        "repo_id": str(uuid.uuid4()),
        "pr_number": 7,
        "base_sha": "b",
        "head_sha": "h",
        "full_name": "owner/r",
    }
    await mod.handle_pr_merge_update("j", payload)
    assert call_log == ["index_and_cache", "find_affected_clusters"]
    assert captured["backfill_calls"][0]["repo_path"] == "/tmp/repo"
    assert captured["backfill_calls"][0]["head_sha"] == "h"


async def test_backfill_failure_falls_through_to_cache_miss_full_scan(
    monkeypatch: pytest.MonkeyPatch, _patched: None, captured: dict[str, Any]
) -> None:
    """When the backfill raises, the dispatcher must not crash.

    The downstream ``_find_affected_clusters`` will return ``None``
    (since head_rows is still empty), and the existing cache-miss
    branch then triggers a full scan. This preserves today's
    correctness guarantee — the cost of a failed backfill is one extra
    full scan, not data loss.
    """

    async def _exploding_backfill(**_kw: Any) -> int:
        raise RuntimeError("synthetic: indexer crash")

    async def _cache_miss(*_a: Any, **_kw: Any) -> set[str] | None:
        return None  # mimics empty head_rows after a failed backfill

    monkeypatch.setattr(mod, "index_and_cache", _exploding_backfill)
    monkeypatch.setattr(mod, "_find_affected_clusters", _cache_miss)

    payload = {
        "org_id": str(uuid.uuid4()),
        "repo_id": str(uuid.uuid4()),
        "pr_number": 7,
        "base_sha": "b",
        "head_sha": "h",
        "full_name": "owner/r",
    }
    await mod.handle_pr_merge_update("j", payload)
    # The dispatcher did not crash → full-scan fallback fired.
    assert captured["scan_triggered"] is True
    assert "cache_miss" in (captured["scan_reason"] or "")
    # And the narrow path did NOT fire.
    assert captured["narrow_payload"] is None


async def test_backfill_skipped_when_repo_has_no_path(
    monkeypatch: pytest.MonkeyPatch, _patched: None, captured: dict[str, Any]
) -> None:
    """A repo row without a ``path`` (never cloned) must not crash the dispatcher.

    The helper logs ``pr_merge_update_backfill_skipped_no_path`` and
    returns silently; ``_find_affected_clusters`` then runs as usual
    (and probably hits the cache-miss branch). The point: the indexer
    is never called against a None path, which would explode lower
    down the stack.
    """

    async def _no_path_repo_and_org(
        _db: Any, *, org_id: uuid.UUID, repo_id: uuid.UUID
    ) -> tuple[Any, Any]:
        class _Repo:
            github_repo_full_name = "owner/r"
            path = None  # ← the case under test
            head_sha = "TRACKED"

        class _Org:
            id = org_id

        return _Repo(), _Org()

    indexer_calls: list[Any] = []

    async def _track_indexer(**_kw: Any) -> int:
        indexer_calls.append(_kw)
        return 0

    async def _empty(*_a: Any, **_kw: Any) -> set[str] | None:
        return None

    monkeypatch.setattr(mod, "_load_repo_and_org", _no_path_repo_and_org)
    monkeypatch.setattr(mod, "index_and_cache", _track_indexer)
    monkeypatch.setattr(mod, "_find_affected_clusters", _empty)

    payload = {
        "org_id": str(uuid.uuid4()),
        "repo_id": str(uuid.uuid4()),
        "pr_number": 7,
        "base_sha": "b",
        "head_sha": "h",
        "full_name": "owner/r",
    }
    await mod.handle_pr_merge_update("j", payload)
    assert indexer_calls == []  # indexer never invoked
    # Cache-miss fallback still runs.
    assert captured["scan_triggered"] is True


# --- _find_affected_clusters algorithm: added / modified / removed -----------


class _FakeClusterCacheRow:
    """Minimal stand-in for a ``ClusterCache`` row used by the algorithm."""

    def __init__(self, cluster_id: str, signature: str, files: list[str]) -> None:
        self.cluster_id = cluster_id
        self.signature = signature
        self.files = files


class _FakeClusterCacheRepo:
    """Returns pre-canned rows per SHA without hitting Postgres."""

    def __init__(self, by_sha: dict[str, list[_FakeClusterCacheRow]]) -> None:
        self._by_sha = by_sha

    @classmethod
    def install(
        cls,
        monkeypatch: pytest.MonkeyPatch,
        *,
        base_rows: list[_FakeClusterCacheRow],
        head_rows: list[_FakeClusterCacheRow],
    ) -> None:
        repo = cls({"BASE": base_rows, "HEAD": head_rows})

        def _factory(_db: Any, *, org_id: Any) -> Any:
            return repo

        monkeypatch.setattr(mod, "ClusterCacheRepository", _factory)

    async def list_for_repo_sha(self, *, repo_id: uuid.UUID, head_sha: str):  # type: ignore[no-untyped-def]
        return list(self._by_sha.get(head_sha, []))


async def test_find_affected_clusters_detects_removed_cluster(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A cluster present at base but absent at head should appear in
    the affected set so the narrow handler's reconciler can soft-
    delete the matching feature with a SHA stamp.
    """
    base = [
        _FakeClusterCacheRow("c-auth", "sig-auth", ["src/auth/router.py"]),
        _FakeClusterCacheRow("c-reminders", "sig-reminders", ["src/reminders/x.py"]),
    ]
    head = [
        # Reminders cluster is gone — only auth survives at head.
        _FakeClusterCacheRow("c-auth", "sig-auth", ["src/auth/router.py"]),
    ]
    _FakeClusterCacheRepo.install(monkeypatch, base_rows=base, head_rows=head)
    result = await mod._find_affected_clusters(
        db=object(),
        org_id=uuid.uuid4(),
        repo_id=uuid.uuid4(),
        base_sha="BASE",
        head_sha="HEAD",
        changed_paths={"src/reminders/x.py"},
    )
    assert result is not None
    affected, effective_base = result
    # Reminders was REMOVED at head — must be flagged.
    assert affected == {"c-reminders"}
    assert effective_base == "BASE"


async def test_find_affected_clusters_added_modified_removed_combine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """All three branches fire in one PR — added, modified, removed."""
    base = [
        _FakeClusterCacheRow("c-auth", "sig-auth-old", ["src/auth/router.py"]),
        _FakeClusterCacheRow("c-billing", "sig-billing", ["src/billing/router.py"]),
        _FakeClusterCacheRow("c-old", "sig-old", ["src/old/legacy.py"]),
    ]
    head = [
        # Auth's signature changed (modified — files match changed_paths)
        _FakeClusterCacheRow("c-auth", "sig-auth-old", ["src/auth/router.py"]),
        # Billing untouched
        _FakeClusterCacheRow("c-billing", "sig-billing", ["src/billing/router.py"]),
        # c-old was deleted — not in head
        # c-new added with a brand-new signature
        _FakeClusterCacheRow("c-new", "sig-new", ["src/search/router.py"]),
    ]
    _FakeClusterCacheRepo.install(monkeypatch, base_rows=base, head_rows=head)
    result = await mod._find_affected_clusters(
        db=object(),
        org_id=uuid.uuid4(),
        repo_id=uuid.uuid4(),
        base_sha="BASE",
        head_sha="HEAD",
        changed_paths={"src/auth/router.py", "src/search/router.py"},
    )
    assert result is not None
    affected, _effective_base = result
    # c-auth (modified — file touched), c-new (added), c-old (removed).
    # c-billing untouched.
    assert affected == {"c-auth", "c-new", "c-old"}


async def test_find_affected_clusters_falls_back_to_tracked_head_sha(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When ``base_sha`` has no rows (main moved between scans), the
    algorithm must fall back to ``tracked_head_sha`` so the narrow
    path doesn't degrade into a full scan.

    Sequence: baseline scan ran at SHA-A → cluster_cache populated for
    SHA-A. Some chore commits landed on main moving to SHA-B (no
    webhook delivered to Phase-2 backfill). A PR opens with
    ``base_sha=SHA-B`` (no rows) and merges to ``head_sha=SHA-C``.
    Effective base falls back to ``tracked_head_sha=SHA-A`` —
    affected set is computed against that, and the returned
    ``effective_base_sha`` is SHA-A so the narrow handler downstream
    knows where to look up removed-cluster signatures.
    """
    # Repo rows are keyed by the simulated SHAs. ``base_sha="SHA_B"``
    # is intentionally absent — the fake only returns rows for SHA_A
    # and SHA_C below.
    _FakeClusterCacheRepo.install(
        monkeypatch,
        base_rows=[],
        head_rows=[
            _FakeClusterCacheRow("c-auth", "sig-auth", ["src/auth/router.py"]),
        ],
    )

    class _MultiShaRepo:
        async def list_for_repo_sha(
            self, *, repo_id: uuid.UUID, head_sha: str
        ) -> list[_FakeClusterCacheRow]:
            if head_sha == "SHA_A":  # baseline scan SHA
                return [
                    _FakeClusterCacheRow("c-auth", "sig-auth", ["src/auth/router.py"]),
                    _FakeClusterCacheRow("c-old", "sig-old", ["src/old/x.py"]),
                ]
            if head_sha == "SHA_C":  # merge SHA, just-backfilled
                return [
                    _FakeClusterCacheRow("c-auth", "sig-auth", ["src/auth/router.py"]),
                ]
            return []  # SHA_B (chore-commit base) has no rows

    monkeypatch.setattr(mod, "ClusterCacheRepository", lambda *_a, **_kw: _MultiShaRepo())
    result = await mod._find_affected_clusters(
        db=object(),
        org_id=uuid.uuid4(),
        repo_id=uuid.uuid4(),
        base_sha="SHA_B",  # ← chore-commit base, no rows
        head_sha="SHA_C",
        changed_paths={"src/old/x.py"},
        tracked_head_sha="SHA_A",  # ← baseline scan SHA
    )
    assert result is not None
    affected, effective_base = result
    # c-old is removed (in SHA_A's rows, not in SHA_C's). c-auth is
    # unchanged (same sig). With the fallback, c-old gets surfaced —
    # without the fallback, base_rows would be empty and the
    # algorithm would return None (cache miss).
    assert affected == {"c-old"}
    # The returned effective_base_sha is the fallback, so the narrow
    # handler's loader looks up removed-cluster signatures there.
    assert effective_base == "SHA_A"


async def test_find_affected_clusters_returns_none_when_both_shas_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When neither base_sha NOR tracked_head_sha has rows, the
    fallback can't save us — must return None so the caller triggers
    a full scan.
    """

    class _EmptyRepo:
        async def list_for_repo_sha(
            self, *, repo_id: uuid.UUID, head_sha: str
        ) -> list[_FakeClusterCacheRow]:
            return []

    monkeypatch.setattr(mod, "ClusterCacheRepository", lambda *_a, **_kw: _EmptyRepo())
    result = await mod._find_affected_clusters(
        db=object(),
        org_id=uuid.uuid4(),
        repo_id=uuid.uuid4(),
        base_sha="SHA_B",
        head_sha="SHA_C",
        changed_paths={"src/anything.py"},
        tracked_head_sha="SHA_A",  # ← also empty per the fake
    )
    assert result is None
