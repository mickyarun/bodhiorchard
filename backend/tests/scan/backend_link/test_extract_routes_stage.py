# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Unit tests for the per-repo ``extract_routes`` stage.

Stubs out ``with_session`` and the two repositories the stage talks to,
then drives it against a synthetic backend worktree at ``tmp_path``.
The central invariant is that a re-invocation with the same
``head_sha`` short-circuits via the cache-hit predicate — without that,
the SHA-keyed cache buys nothing on re-scan.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pytest

from app.models.repo_layer import RepoLayer
from app.services.scan.stages import StageContext, extract_routes


class _FakeSession:
    """Async-context-manager session that records commits."""

    def __init__(self) -> None:
        self.committed = False

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        pass

    async def __aenter__(self) -> _FakeSession:
        return self

    async def __aexit__(self, *_: Any) -> None:
        pass


class _FakeTracked:
    """Stand-in TrackedRepository row used by the stage's layer check."""

    def __init__(self, repo_layer: RepoLayer | None) -> None:
        self.repo_layer = repo_layer


class _FakeTrackedRepo:
    """Stub :class:`TrackedRepoRepository` that returns a fixed row."""

    def __init__(self, tracked: _FakeTracked | None) -> None:
        self._tracked = tracked

    async def get_by_id(self, _repo_id: uuid.UUID) -> _FakeTracked | None:
        return self._tracked


class _FakeCacheRepo:
    """Stub :class:`BackendRouteCacheRepository` recording read/write calls.

    ``cached_shas`` simulates the rows already in the cache; ``replace_calls``
    records every write so the test can assert the cache-hit branch never
    triggered a write.
    """

    def __init__(self, cached_shas: set[str]) -> None:
        self._cached_shas = set(cached_shas)
        self.replace_calls: list[tuple[uuid.UUID, str, int]] = []

    async def has_rows_for_sha(self, *, repo_id: uuid.UUID, head_sha: str) -> bool:  # noqa: ARG002
        return head_sha in self._cached_shas

    async def replace_for_repo_sha(
        self, *, repo_id: uuid.UUID, head_sha: str, records: Any
    ) -> int:
        materialised = list(records)
        self.replace_calls.append((repo_id, head_sha, len(materialised)))
        self._cached_shas.add(head_sha)
        return len(materialised)


def _patch_session(monkeypatch: pytest.MonkeyPatch) -> _FakeSession:
    session = _FakeSession()

    @asynccontextmanager
    async def _fake_with_session(_org_id: uuid.UUID) -> Any:
        yield session

    monkeypatch.setattr(extract_routes, "with_session", _fake_with_session)
    return session


def _write_backend_worktree(root: Path) -> None:
    """Plant a couple of NestJS-shaped route files under ``src/``.

    The regex skip-list requires the file to live in a recognisable
    routing directory (``controllers/``, ``routes/``, …) so a flat
    ``src/foo.ts`` is silently dropped — that's by design.
    """
    routes = root / "src" / "controllers"
    routes.mkdir(parents=True)
    (routes / "users.ts").write_text(
        '@Controller("/api")\n'
        "class UsersController {\n"
        '  @Get("/users") list() {}\n'
        '  @Post("/users") create() {}\n'
        "}\n"
    )
    (routes / "orders.ts").write_text('router.get("/orders", () => {});\n')


def _make_ctx(tmp_path: Path) -> StageContext:
    return StageContext(run_id="test-run", repo_path=str(tmp_path), repo_name="my-backend")


def _make_config(repo_id: uuid.UUID, head_sha: str | None) -> dict[str, Any]:
    cfg: dict[str, Any] = {
        "v2_org_id": uuid.uuid4(),
        "v2_scan_id": uuid.uuid4(),
        "v2_repo_id": repo_id,
    }
    if head_sha is not None:
        cfg["ingest_head_sha"] = head_sha
    return cfg


# ───────────────────────── happy path ─────────────────────────


async def test_cache_miss_walks_worktree_and_writes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """First invocation on a fresh SHA writes the cache and reports counts."""
    _write_backend_worktree(tmp_path)
    _patch_session(monkeypatch)

    cache = _FakeCacheRepo(cached_shas=set())
    tracked = _FakeTracked(repo_layer=RepoLayer.BACKEND)

    monkeypatch.setattr(
        extract_routes,
        "TrackedRepoRepository",
        lambda _db, *, org_id: _FakeTrackedRepo(tracked),  # noqa: ARG005
    )
    monkeypatch.setattr(
        extract_routes,
        "BackendRouteCacheRepository",
        lambda _db, *, org_id: cache,  # noqa: ARG005
    )

    repo_id = uuid.uuid4()
    out = await extract_routes.run(_make_ctx(tmp_path), [], _make_config(repo_id, "deadbee"))

    assert out.communities == []
    assert out.extras["kept_count"] >= 1, "synthetic worktree declares routes"
    assert "skipped_unchanged" not in out.extras
    assert len(cache.replace_calls) == 1
    written_repo_id, written_sha, written_count = cache.replace_calls[0]
    assert written_repo_id == repo_id
    assert written_sha == "deadbee"
    assert written_count == out.extras["kept_count"]


async def test_cache_hit_short_circuits(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Second call on the same ``head_sha`` must NOT re-walk or re-write.

    This is the core invariant of the redesign: re-scanning the same
    commit is a single ``EXISTS`` lookup. If this regresses, every scan
    rewrites every row and the cache buys nothing.
    """
    _write_backend_worktree(tmp_path)
    _patch_session(monkeypatch)

    cache = _FakeCacheRepo(cached_shas={"deadbee"})  # already cached
    tracked = _FakeTracked(repo_layer=RepoLayer.BACKEND)

    monkeypatch.setattr(
        extract_routes,
        "TrackedRepoRepository",
        lambda _db, *, org_id: _FakeTrackedRepo(tracked),  # noqa: ARG005
    )
    monkeypatch.setattr(
        extract_routes,
        "BackendRouteCacheRepository",
        lambda _db, *, org_id: cache,  # noqa: ARG005
    )

    out = await extract_routes.run(_make_ctx(tmp_path), [], _make_config(uuid.uuid4(), "deadbee"))

    assert out.extras.get("skipped_unchanged") is True
    assert out.extras["head_sha"] == "deadbee"
    assert cache.replace_calls == [], "cache hit must not write"


# ───────────────────────── skip paths ─────────────────────────


async def test_non_backend_repo_skips(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Frontend / processor / etc. layers exit before touching the cache."""
    _write_backend_worktree(tmp_path)
    _patch_session(monkeypatch)

    cache = _FakeCacheRepo(cached_shas=set())
    tracked = _FakeTracked(repo_layer=RepoLayer.FRONTEND)

    monkeypatch.setattr(
        extract_routes,
        "TrackedRepoRepository",
        lambda _db, *, org_id: _FakeTrackedRepo(tracked),  # noqa: ARG005
    )
    monkeypatch.setattr(
        extract_routes,
        "BackendRouteCacheRepository",
        lambda _db, *, org_id: cache,  # noqa: ARG005
    )

    out = await extract_routes.run(_make_ctx(tmp_path), [], _make_config(uuid.uuid4(), "deadbee"))

    assert out.extras.get("skipped") is True
    assert out.extras.get("skipped_reason") == "non-backend repo"
    assert cache.replace_calls == []


async def test_missing_head_sha_skips_persistence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """No SHA = nothing to key the cache by → skip without writing."""
    _write_backend_worktree(tmp_path)
    _patch_session(monkeypatch)

    cache = _FakeCacheRepo(cached_shas=set())
    tracked = _FakeTracked(repo_layer=RepoLayer.BACKEND)

    monkeypatch.setattr(
        extract_routes,
        "TrackedRepoRepository",
        lambda _db, *, org_id: _FakeTrackedRepo(tracked),  # noqa: ARG005
    )
    monkeypatch.setattr(
        extract_routes,
        "BackendRouteCacheRepository",
        lambda _db, *, org_id: cache,  # noqa: ARG005
    )

    out = await extract_routes.run(_make_ctx(tmp_path), [], _make_config(uuid.uuid4(), ""))

    assert out.extras.get("skipped") is True
    assert "head_sha" in (out.extras.get("skipped_reason") or "")
    assert cache.replace_calls == []


async def test_v2_context_missing_skips(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Sandbox runs (no ``v2_org_id`` / ``v2_scan_id``) no-op cleanly."""
    _patch_session(monkeypatch)
    out = await extract_routes.run(_make_ctx(tmp_path), [], {})
    assert out.communities == []
    assert out.extras.get("skipped") is True
