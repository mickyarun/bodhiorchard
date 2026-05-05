# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Unit tests for the global ``backend_link`` phase.

Two synthetic repos at ``tmp_path``: a frontend repo with a feature
seed file calling ``axios.get("/api/users")``, and a backend repo
whose cached routes declare ``/api/users``. Repositories and the
session helper are stubbed; the phase is asked to walk the frontend
and produce ``feature_to_repo`` BACKEND link writes.

The test owns ``replace_backend_links`` — every call is recorded in a
list — so the assertion is purely on what the linker decided to write.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pytest

from app.models.repo_layer import RepoLayer
from app.services.scan.phase_impls import backend_link as phase


class _FakeSession:
    async def commit(self) -> None:
        pass

    async def rollback(self) -> None:
        pass

    async def __aenter__(self) -> _FakeSession:
        return self

    async def __aexit__(self, *_: Any) -> None:
        pass


class _FakeTracked:
    """Stand-in TrackedRepository row.

    The phase reads ``id``, ``name``, ``path``, and ``head_sha`` (for
    backends). All other fields on the real model are unused by the
    linker so we don't need to invent them here.
    """

    def __init__(
        self,
        *,
        name: str,
        path: str,
        head_sha: str | None,
        repo_id: uuid.UUID | None = None,
    ) -> None:
        self.id = repo_id or uuid.uuid4()
        self.name = name
        self.path = path
        self.head_sha = head_sha


class _FakeTrackedRepoRepo:
    """Stub :class:`TrackedRepoRepository` returning fixed lists per layer."""

    def __init__(self, *, frontends: list[_FakeTracked], backends: list[_FakeTracked]) -> None:
        self._frontends = frontends
        self._backends = backends

    async def list_by_layer(self, layer: RepoLayer) -> list[_FakeTracked]:
        if layer is RepoLayer.FRONTEND:
            return list(self._frontends)
        if layer is RepoLayer.BACKEND:
            return list(self._backends)
        return []


class _FakeCacheRow:
    """Subset of :class:`BackendRouteCache` the phase reads."""

    def __init__(self, normalised_path: str, file_path: str) -> None:
        self.normalised_path = normalised_path
        self.file_path = file_path


class _FakeCacheRepo:
    """Stub :class:`BackendRouteCacheRepository` returning fixed rows."""

    def __init__(self, rows_by_repo: dict[uuid.UUID, list[_FakeCacheRow]]) -> None:
        self._rows = rows_by_repo

    async def list_for_repo_sha(self, *, repo_id: uuid.UUID, head_sha: str) -> list[_FakeCacheRow]:  # noqa: ARG002
        return list(self._rows.get(repo_id, []))


class _FakeFeature:
    def __init__(self, fid: uuid.UUID, feature_title: str = "Feature: stub") -> None:
        self.id = fid
        self.feature_title = feature_title


class _FakePrimaryLink:
    """Stand-in for the PRIMARY ``FeatureToRepo`` row.

    Only ``code_locations`` is read by the phase; the linker walks
    those paths off the worktree to build the seed set for path
    extraction.
    """

    def __init__(self, code_locations: dict[str, list[str]] | None) -> None:
        self.code_locations = code_locations


class _FakeFeatureRepo:
    """Stub :class:`FeatureRepository` returning a fixed pair list."""

    def __init__(self, pairs: list[tuple[_FakeFeature, _FakePrimaryLink]]) -> None:
        self._pairs = pairs

    async def list_primary_pairs_for_repo(
        self, _repo_id: uuid.UUID
    ) -> list[tuple[_FakeFeature, _FakePrimaryLink]]:
        return list(self._pairs)


def _patch_session(monkeypatch: pytest.MonkeyPatch) -> None:
    @asynccontextmanager
    async def _fake_with_session(_org_id: uuid.UUID) -> Any:
        yield _FakeSession()

    monkeypatch.setattr(phase, "with_session", _fake_with_session)


def _build_synthetic_repos(tmp_path: Path) -> tuple[Path, Path]:
    """Plant a frontend repo + a backend repo and return their roots."""
    frontend = tmp_path / "frontend"
    backend = tmp_path / "backend"
    (frontend / "src").mkdir(parents=True)
    (backend / "src" / "controllers").mkdir(parents=True)
    # Frontend feature seed: a single file calling /api/users.
    (frontend / "src" / "users.ts").write_text('await axios.get("/api/users");\n')
    # Backend declaration — only used to seed the cached row's file_path.
    (backend / "src" / "controllers" / "users.ts").write_text('@Get("/api/users") list() {}\n')
    return frontend, backend


# ───────────────────────── tests ─────────────────────────


async def test_global_phase_writes_backend_link_for_matched_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Frontend seed file calls ``/api/users``; cached backend declares it.

    Expected outcome: one ``replace_backend_links`` call for the feature,
    pointing at the backend repo's id with ``["/api/users"]``.
    """
    frontend_root, _ = _build_synthetic_repos(tmp_path)

    backend_id = uuid.uuid4()
    frontend = _FakeTracked(name="fe", path=str(frontend_root), head_sha="ff")
    backend = _FakeTracked(name="be", path="/unused", head_sha="bb", repo_id=backend_id)

    cache = _FakeCacheRepo(
        rows_by_repo={
            backend_id: [
                _FakeCacheRow(
                    normalised_path="/api/users",
                    file_path="src/controllers/users.ts",
                ),
            ]
        }
    )
    tracked_repo = _FakeTrackedRepoRepo(frontends=[frontend], backends=[backend])

    monkeypatch.setattr(
        phase,
        "TrackedRepoRepository",
        lambda _db, *, org_id: tracked_repo,  # noqa: ARG005
    )
    monkeypatch.setattr(
        phase,
        "BackendRouteCacheRepository",
        lambda _db, *, org_id: cache,  # noqa: ARG005
    )

    feature = _FakeFeature(uuid.uuid4())
    primary = _FakePrimaryLink(code_locations={"frontend": ["src/users.ts"]})
    feature_repo = _FakeFeatureRepo([(feature, primary)])

    monkeypatch.setattr(
        phase,
        "FeatureRepository",
        lambda _db, *, org_id: feature_repo,  # noqa: ARG005
    )

    writes: list[
        tuple[uuid.UUID, str, list[tuple[uuid.UUID, list[str], dict[str, list[str]] | None]]]
    ] = []

    async def _fake_replace(
        _db: Any,
        *,
        feature_id: uuid.UUID,
        feature_title: str,
        backend_repos: list[tuple[uuid.UUID, list[str], dict[str, list[str]] | None]],
    ) -> None:
        writes.append((feature_id, feature_title, list(backend_repos)))

    monkeypatch.setattr(phase, "replace_backend_links", _fake_replace)

    async def _fake_count(_db: Any, *, feature_id: uuid.UUID) -> int:  # noqa: ARG001
        return 0

    monkeypatch.setattr(phase, "count_backend_links", _fake_count)

    _patch_session(monkeypatch)

    counters = await phase.run_backend_link(org_id=uuid.uuid4(), scan_id=uuid.uuid4())

    assert counters["frontend_repos"] == 1
    assert counters["backend_repos_indexed"] == 1
    assert counters["features_processed"] == 1
    assert counters["features_linked"] == 1
    assert len(writes) == 1
    written_feature_id, written_title, buckets = writes[0]
    assert written_feature_id == feature.id
    assert written_title == feature.feature_title
    assert buckets == [
        (backend_id, ["/api/users"], {"backend": ["src/controllers/users.ts"]}),
    ]


async def test_no_match_clears_existing_backend_rows(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Feature whose calls don't match any cached route gets its BACKEND rows cleared.

    The phase still fires ``replace_backend_links`` with an empty
    ``backend_repos`` list — that's the contract for "no links
    anymore" and keeps stale rows from outliving a rename.
    """
    frontend_root = tmp_path / "frontend"
    (frontend_root / "src").mkdir(parents=True)
    (frontend_root / "src" / "users.ts").write_text('await axios.get("/some/other/path");\n')

    frontend = _FakeTracked(name="fe", path=str(frontend_root), head_sha="ff")
    backend_id = uuid.uuid4()
    backend = _FakeTracked(name="be", path="/unused", head_sha="bb", repo_id=backend_id)

    cache = _FakeCacheRepo(
        rows_by_repo={
            backend_id: [
                _FakeCacheRow(
                    normalised_path="/api/users",
                    file_path="src/controllers/users.ts",
                ),
            ]
        }
    )
    tracked_repo = _FakeTrackedRepoRepo(frontends=[frontend], backends=[backend])

    monkeypatch.setattr(
        phase,
        "TrackedRepoRepository",
        lambda _db, *, org_id: tracked_repo,  # noqa: ARG005
    )
    monkeypatch.setattr(
        phase,
        "BackendRouteCacheRepository",
        lambda _db, *, org_id: cache,  # noqa: ARG005
    )

    feature = _FakeFeature(uuid.uuid4())
    primary = _FakePrimaryLink(code_locations={"frontend": ["src/users.ts"]})
    feature_repo = _FakeFeatureRepo([(feature, primary)])

    monkeypatch.setattr(
        phase,
        "FeatureRepository",
        lambda _db, *, org_id: feature_repo,  # noqa: ARG005
    )

    writes: list[
        tuple[uuid.UUID, str, list[tuple[uuid.UUID, list[str], dict[str, list[str]] | None]]]
    ] = []

    async def _fake_replace(
        _db: Any,
        *,
        feature_id: uuid.UUID,
        feature_title: str,
        backend_repos: list[tuple[uuid.UUID, list[str], dict[str, list[str]] | None]],
    ) -> None:
        writes.append((feature_id, feature_title, list(backend_repos)))

    monkeypatch.setattr(phase, "replace_backend_links", _fake_replace)

    async def _fake_count(_db: Any, *, feature_id: uuid.UUID) -> int:  # noqa: ARG001
        return 0

    monkeypatch.setattr(phase, "count_backend_links", _fake_count)

    _patch_session(monkeypatch)

    counters = await phase.run_backend_link(org_id=uuid.uuid4(), scan_id=uuid.uuid4())

    assert counters["features_processed"] == 1
    assert counters["features_linked"] == 0
    # One write call, but with an empty bucket list (clears stale rows).
    assert len(writes) == 1
    assert writes[0][0] == feature.id
    assert writes[0][2] == []


async def test_backend_without_head_sha_excluded_from_index(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A backend repo with no ``head_sha`` is skipped during index assembly.

    Its routes can't be safely keyed in the cache yet, so they
    contribute zero entries to ``BackendIndex`` and the counter
    reflects only the SHA-having backends.
    """
    frontend_root, _ = _build_synthetic_repos(tmp_path)

    frontend = _FakeTracked(name="fe", path=str(frontend_root), head_sha="ff")
    no_sha_backend = _FakeTracked(name="be", path="/unused", head_sha=None)

    cache = _FakeCacheRepo(rows_by_repo={})
    tracked_repo = _FakeTrackedRepoRepo(frontends=[frontend], backends=[no_sha_backend])

    monkeypatch.setattr(
        phase,
        "TrackedRepoRepository",
        lambda _db, *, org_id: tracked_repo,  # noqa: ARG005
    )
    monkeypatch.setattr(
        phase,
        "BackendRouteCacheRepository",
        lambda _db, *, org_id: cache,  # noqa: ARG005
    )

    feature_repo = _FakeFeatureRepo([])
    monkeypatch.setattr(
        phase,
        "FeatureRepository",
        lambda _db, *, org_id: feature_repo,  # noqa: ARG005
    )

    async def _fake_replace(_db: Any, **_kw: Any) -> None:
        pass

    monkeypatch.setattr(phase, "replace_backend_links", _fake_replace)

    _patch_session(monkeypatch)

    counters = await phase.run_backend_link(org_id=uuid.uuid4(), scan_id=uuid.uuid4())

    assert counters["indexed_routes"] == 0
    assert counters["features_processed"] == 0
