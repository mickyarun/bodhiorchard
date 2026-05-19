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

"""Dispatcher cap on ``handle_pr_merge_delivery``.

When the PR-merge dispatcher identifies *N* affected clusters:

* ``N == 0`` → no-op (no narrow synth, no full scan).
* ``0 < N <= NARROW_CAP`` → :func:`run_narrow_synthesis` is called
  inline with the affected signatures.
* ``N > NARROW_CAP`` → :func:`_trigger_repo_scan` is called and the
  narrow path is skipped.

Tests target the dispatcher branch points only — the narrow synth
itself is covered by ``test_pr_narrow_synthesis``.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import Any

import pytest

from app.services.scan import pr_merge_update as mod
from app.services.scan.pr_narrow_synthesis import (
    NarrowSynthesisOutcome,
    NarrowSynthesisParams,
)


@pytest.fixture
def captured() -> dict[str, Any]:
    return {
        "narrow_params": None,
        "scan_triggered": False,
        "scan_reason": None,
        "backfill_calls": [],
    }


@pytest.fixture
def _patched(monkeypatch: pytest.MonkeyPatch, captured: dict[str, Any]) -> None:
    """Stub every IO entry-point the dispatcher reaches plus the two
    sinks (narrow + scan).

    Per-test overrides of ``_find_affected_clusters`` are still required
    — that helper is the *behaviour under test*. The other DB helpers
    (``_load_repo_and_org``, ``_fetch_changed_paths``) get the same
    no-op stub so a future test author can't accidentally hit Postgres
    or the GitHub API.
    """

    async def _fake_trigger_scan(**kw: Any) -> None:
        captured["scan_triggered"] = True
        captured["scan_reason"] = kw.get("reason")

    async def _fake_no_paths(*_a: Any, **_kw: Any) -> set[str]:
        return set()

    async def _fake_index_and_cache(
        *, org_id: Any, repo_id: Any, repo_path: str, head_sha: str
    ) -> int:
        captured["backfill_calls"].append(
            {"repo_id": str(repo_id), "repo_path": repo_path, "head_sha": head_sha}
        )
        return 3  # arbitrary non-zero row count

    async def _fake_run_narrow(params: NarrowSynthesisParams) -> NarrowSynthesisOutcome:
        captured["narrow_params"] = params
        return NarrowSynthesisOutcome(
            branch="synthesised", inserted=1, updated=0, revived=0, inactivated=0
        )

    monkeypatch.setattr(mod, "_trigger_repo_scan", _fake_trigger_scan)
    monkeypatch.setattr(mod, "_load_repo_and_org", _fake_repo_and_org)
    monkeypatch.setattr(mod, "_fetch_changed_paths", _fake_no_paths)
    monkeypatch.setattr(mod, "index_and_cache", _fake_index_and_cache)
    monkeypatch.setattr(mod, "run_narrow_synthesis", _fake_run_narrow)


def _install_replay_row(monkeypatch: pytest.MonkeyPatch, payload: dict[str, Any]) -> None:
    """Stub :func:`handle_pr_merge_delivery`'s WebhookLog lookup to
    return a row with the given payload — sidesteps the DB.
    """
    org_id = uuid.UUID(payload["org_id"])
    repo_id = uuid.UUID(payload["repo_id"])

    class _FakeRow:
        delivery_id = "d1"
        event_type = payload.get("event_type", "pull_request")

        def __init__(self) -> None:
            self.org_id = org_id
            self.repo_id = repo_id
            self.payload = {
                "pr_number": payload["pr_number"],
                "base_sha": payload["base_sha"],
                "head_sha": payload["head_sha"],
                "full_name": payload.get("full_name", "owner/r"),
            }

    class _FakeRepo:
        def __init__(self, *_a: Any, **_kw: Any) -> None:
            pass

        async def find_by_delivery_id(self, _did: str) -> Any:
            return _FakeRow()

    @asynccontextmanager
    async def _fake_session() -> Any:
        yield object()

    monkeypatch.setattr(mod, "WebhookLogRepository", _FakeRepo)
    # Two AsyncSessionLocal contexts are opened in handle_pr_merge_delivery
    # → _run_dispatch. A single stub works for both because nothing
    # touches the yielded session beyond passing it to the patched
    # repo factories.
    monkeypatch.setattr(mod, "AsyncSessionLocal", _fake_session)


async def test_dispatcher_picks_narrow_under_cap(
    monkeypatch: pytest.MonkeyPatch, _patched: None, captured: dict[str, Any]
) -> None:
    """``len(affected) <= NARROW_CAP`` → narrow path, no full scan."""
    affected = {f"sig-{i}" for i in range(mod.NARROW_CAP)}  # exactly == cap

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
    _install_replay_row(monkeypatch, payload)
    await mod.handle_pr_merge_delivery("d1")
    assert captured["scan_triggered"] is False
    assert captured["narrow_params"] is not None
    params: NarrowSynthesisParams = captured["narrow_params"]
    assert len(params.affected_signatures) == mod.NARROW_CAP
    # Affected signatures are sorted for deterministic comparison.
    assert params.affected_signatures == sorted(affected)


async def test_dispatcher_falls_back_to_full_scan_above_cap(
    monkeypatch: pytest.MonkeyPatch, _patched: None, captured: dict[str, Any]
) -> None:
    """``len(affected) > NARROW_CAP`` → full ``start_scan`` path, no narrow."""
    affected = {f"sig-{i}" for i in range(mod.NARROW_CAP + 1)}

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
    _install_replay_row(monkeypatch, payload)
    await mod.handle_pr_merge_delivery("d1")
    assert captured["scan_triggered"] is True
    assert captured["narrow_params"] is None
    assert "above narrow cap" in (captured["scan_reason"] or "")


async def test_dispatcher_noop_when_no_clusters_affected(
    monkeypatch: pytest.MonkeyPatch, _patched: None, captured: dict[str, Any]
) -> None:
    """``len(affected) == 0`` → neither path runs."""

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
    _install_replay_row(monkeypatch, payload)
    await mod.handle_pr_merge_delivery("d1")
    assert captured["scan_triggered"] is False
    assert captured["narrow_params"] is None


async def test_dispatcher_raises_when_narrow_synthesis_fails(
    monkeypatch: pytest.MonkeyPatch, _patched: None, captured: dict[str, Any]
) -> None:
    """A failed Claude run inside narrow synth must propagate so the
    worker flips the WebhookLog row to ``failed``. Phase 4 swallowed
    this; Phase 5 surfaces it.
    """
    affected = {"sig-1"}

    async def _resolved(*_a: Any, **_kw: Any) -> tuple[set[str], str] | None:
        return (affected, "BASE")

    async def _failed_narrow(params: NarrowSynthesisParams) -> NarrowSynthesisOutcome:
        captured["narrow_params"] = params
        return NarrowSynthesisOutcome(branch="synthesised", error="claude boom")

    monkeypatch.setattr(mod, "_find_affected_clusters", _resolved)
    monkeypatch.setattr(mod, "run_narrow_synthesis", _failed_narrow)

    payload = {
        "org_id": str(uuid.uuid4()),
        "repo_id": str(uuid.uuid4()),
        "pr_number": 7,
        "base_sha": "b",
        "head_sha": "h",
        "full_name": "owner/r",
    }
    _install_replay_row(monkeypatch, payload)
    with pytest.raises(RuntimeError, match="claude boom"):
        await mod.handle_pr_merge_delivery("d1")


async def test_dispatcher_raises_when_replay_row_missing(
    monkeypatch: pytest.MonkeyPatch, _patched: None
) -> None:
    """Worker hands us a delivery_id with no row → typed exception."""

    class _MissingRepo:
        def __init__(self, *_a: Any, **_kw: Any) -> None:
            pass

        async def find_by_delivery_id(self, _did: str) -> Any:
            return None

    @asynccontextmanager
    async def _fake_session() -> Any:
        yield object()

    monkeypatch.setattr(mod, "WebhookLogRepository", _MissingRepo)
    monkeypatch.setattr(mod, "AsyncSessionLocal", _fake_session)

    with pytest.raises(mod.PrMergeDeliveryMissingError):
        await mod.handle_pr_merge_delivery("gone")


async def _fake_repo_and_org(
    _db: Any, *, org_id: uuid.UUID, repo_id: uuid.UUID
) -> tuple[Any, Any]:
    """Minimal stand-in returning truthy repo + org for the dispatcher's early gate."""

    class _Repo:
        github_repo_full_name = "owner/r"
        path = "/tmp/repo"
        head_sha = "TRACKED_HEAD_SHA"

    class _Org:
        id = org_id

    return _Repo(), _Org()


# --- cluster_cache backfill pre-step ----------------------------------------


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
        return ({"sig-1"}, "BASE")

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
    _install_replay_row(monkeypatch, payload)
    await mod.handle_pr_merge_delivery("d1")
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

    async def _cache_miss(*_a: Any, **_kw: Any) -> tuple[set[str], str] | None:
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
    _install_replay_row(monkeypatch, payload)
    await mod.handle_pr_merge_delivery("d1")
    assert captured["scan_triggered"] is True
    assert "cache_miss" in (captured["scan_reason"] or "")
    assert captured["narrow_params"] is None


async def test_backfill_skipped_when_repo_has_no_path(
    monkeypatch: pytest.MonkeyPatch, _patched: None, captured: dict[str, Any]
) -> None:
    """A repo row without a ``path`` (never cloned) must not crash the dispatcher."""

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

    async def _empty(*_a: Any, **_kw: Any) -> tuple[set[str], str] | None:
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
    _install_replay_row(monkeypatch, payload)
    await mod.handle_pr_merge_delivery("d1")
    assert indexer_calls == []  # indexer never invoked
    assert captured["scan_triggered"] is True  # cache-miss fallback still runs


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
    """A cluster present at base but absent at head should appear in the
    affected set so the narrow handler can soft-delete it.
    """
    base = [
        _FakeClusterCacheRow("c-auth", "sig-auth", ["src/auth/router.py"]),
        _FakeClusterCacheRow("c-reminders", "sig-reminders", ["src/reminders/x.py"]),
    ]
    head = [
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
    assert affected == {"sig-reminders"}
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
        _FakeClusterCacheRow("c-auth", "sig-auth-old", ["src/auth/router.py"]),
        _FakeClusterCacheRow("c-billing", "sig-billing", ["src/billing/router.py"]),
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
    assert affected == {"sig-auth-old", "sig-new", "sig-old"}


async def test_find_affected_clusters_falls_back_to_tracked_head_sha(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When ``base_sha`` has no rows (main moved between scans), the
    algorithm must fall back to ``tracked_head_sha``.
    """

    class _MultiShaRepo:
        async def list_for_repo_sha(
            self, *, repo_id: uuid.UUID, head_sha: str
        ) -> list[_FakeClusterCacheRow]:
            if head_sha == "SHA_A":
                return [
                    _FakeClusterCacheRow("c-auth", "sig-auth", ["src/auth/router.py"]),
                    _FakeClusterCacheRow("c-old", "sig-old", ["src/old/x.py"]),
                ]
            if head_sha == "SHA_C":
                return [
                    _FakeClusterCacheRow("c-auth", "sig-auth", ["src/auth/router.py"]),
                ]
            return []

    monkeypatch.setattr(mod, "ClusterCacheRepository", lambda *_a, **_kw: _MultiShaRepo())
    result = await mod._find_affected_clusters(
        db=object(),
        org_id=uuid.uuid4(),
        repo_id=uuid.uuid4(),
        base_sha="SHA_B",
        head_sha="SHA_C",
        changed_paths={"src/old/x.py"},
        tracked_head_sha="SHA_A",
    )
    assert result is not None
    affected, effective_base = result
    assert affected == {"sig-old"}
    assert effective_base == "SHA_A"


async def test_find_affected_clusters_returns_none_when_both_shas_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When neither base_sha NOR tracked_head_sha has rows, return None."""

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
        tracked_head_sha="SHA_A",
    )
    assert result is None
