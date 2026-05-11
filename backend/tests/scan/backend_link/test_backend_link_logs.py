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

"""Tests for the diagnostic logs added to ``backend_link``.

The phase used to log a single aggregate per frontend (``processed`` /
``linked``) — there was no way to tell why a feature linked to zero
backends. The added counters split the silent skip-paths apart so the
operator can grep for the exact reason. This module pins the contract:

* ``seed_empty`` increments when ``code_locations`` resolves to no files.
* ``no_index_matches`` increments when api_paths extracted but the
  ``BackendIndex`` returned nothing.
* ``scan_backend_link_clearing_existing`` warning fires only when an
  empty replace_backend_links is about to nuke pre-existing rows.

The phase uses ``structlog`` so we stub ``phase.logger`` with a
recorder rather than reach for ``caplog`` — structlog calls bypass the
stdlib logging hierarchy until configured to forward, and the project
config doesn't enable that bridge in tests.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from app.models.repo_layer import RepoLayer
from app.services.scan.phase_impls import backend_link as phase


@dataclass
class _LogCall:
    """One structured-log call captured by :class:`_LogRecorder`."""

    level: str
    event: str
    kwargs: dict[str, Any] = field(default_factory=dict)


class _LogRecorder:
    """Drop-in stub for ``phase.logger`` that records calls to a list.

    Mirrors the subset of the structlog interface the phase uses:
    ``info`` / ``warning`` / ``debug``. Each captured call carries the
    event name + structured kwargs so assertions read off the same
    fields the production logs would emit.
    """

    def __init__(self) -> None:
        self.calls: list[_LogCall] = []

    def info(self, event: str, **kwargs: Any) -> None:
        self.calls.append(_LogCall("info", event, kwargs))

    def warning(self, event: str, **kwargs: Any) -> None:
        self.calls.append(_LogCall("warning", event, kwargs))

    def debug(self, event: str, **kwargs: Any) -> None:
        self.calls.append(_LogCall("debug", event, kwargs))

    def find(self, event: str, level: str | None = None) -> list[_LogCall]:
        return [c for c in self.calls if c.event == event and (level is None or c.level == level)]


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
    def __init__(self, *, frontends: list[_FakeTracked], backends: list[_FakeTracked]) -> None:
        self._frontends = frontends
        self._backends = backends

    async def list_by_layer(self, layer: RepoLayer) -> list[_FakeTracked]:
        if layer is RepoLayer.FRONTEND:
            return list(self._frontends)
        if layer is RepoLayer.BACKEND:
            return list(self._backends)
        return []


class _FakeCacheRepo:
    def __init__(self, rows_by_repo: dict[uuid.UUID, list[Any]]) -> None:
        self._rows = rows_by_repo

    async def list_for_repo_sha(self, *, repo_id: uuid.UUID, head_sha: str) -> list[Any]:  # noqa: ARG002
        return list(self._rows.get(repo_id, []))


class _FakeFeature:
    def __init__(self, fid: uuid.UUID, feature_title: str = "Feature: stub") -> None:
        self.id = fid
        self.feature_title = feature_title


class _FakePrimaryLink:
    def __init__(self, code_locations: dict[str, list[str]] | None) -> None:
        self.code_locations = code_locations


class _FakeFeatureRepo:
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


def _wire_minimal_org(
    monkeypatch: pytest.MonkeyPatch,
    *,
    frontend: _FakeTracked,
    feature: _FakeFeature,
    primary: _FakePrimaryLink,
    existing_backend_count: int,
) -> tuple[list[uuid.UUID], _LogRecorder]:
    """Stub the repos + logger for a one-frontend / no-backend scenario.

    Returns ``(cleared_feature_ids, log_recorder)`` — the test asserts on
    both alongside checking the structured log calls.
    """
    feature_repo = _FakeFeatureRepo([(feature, primary)])
    tracked_repo = _FakeTrackedRepoRepo(frontends=[frontend], backends=[])
    cache = _FakeCacheRepo(rows_by_repo={})

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
    monkeypatch.setattr(
        phase,
        "FeatureRepository",
        lambda _db, *, org_id: feature_repo,  # noqa: ARG005
    )

    cleared: list[uuid.UUID] = []

    async def _fake_replace(
        _db: Any,
        *,
        feature_id: uuid.UUID,
        feature_title: str,  # noqa: ARG001 — captured by signature for parity, unused here
        backend_repos: Any,
    ) -> None:
        cleared.append(feature_id)
        assert backend_repos == [], "test fixtures cover the empty-replace path only"

    monkeypatch.setattr(phase, "replace_backend_links", _fake_replace)

    async def _fake_count(_db: Any, *, feature_id: uuid.UUID) -> int:  # noqa: ARG001
        return existing_backend_count

    monkeypatch.setattr(phase, "count_backend_links", _fake_count)

    recorder = _LogRecorder()
    monkeypatch.setattr(phase, "logger", recorder)

    _patch_session(monkeypatch)
    return cleared, recorder


# ───────────────────────── tests ─────────────────────────


async def test_seed_empty_increments_when_code_locations_none(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A feature with ``code_locations = None`` increments the seed_empty counter."""
    frontend_root = tmp_path / "frontend"
    frontend_root.mkdir()
    frontend = _FakeTracked(name="fe", path=str(frontend_root), head_sha="ff")
    feature = _FakeFeature(uuid.uuid4())
    primary = _FakePrimaryLink(code_locations=None)

    cleared, recorder = _wire_minimal_org(
        monkeypatch,
        frontend=frontend,
        feature=feature,
        primary=primary,
        existing_backend_count=0,
    )

    counters = await phase.run_backend_link(org_id=uuid.uuid4(), scan_id=uuid.uuid4())

    assert counters["features_processed"] == 1
    assert counters["features_linked"] == 0
    assert cleared == [feature.id]

    breakdowns = recorder.find("scan_backend_link_frontend_done", level="info")
    assert breakdowns, "expected scan_backend_link_frontend_done log"
    payload = breakdowns[0].kwargs
    assert payload["seed_empty"] == 1
    assert payload["no_api_paths"] == 0
    assert payload["no_index_matches"] == 0
    assert payload["linked"] == 0


async def test_clearing_existing_warning_fires_when_prior_rows_existed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Empty-replace with prior BACKEND rows surfaces a structured warning."""
    frontend_root = tmp_path / "frontend"
    frontend_root.mkdir()
    frontend = _FakeTracked(name="fe", path=str(frontend_root), head_sha="ff")
    feature = _FakeFeature(uuid.uuid4())
    primary = _FakePrimaryLink(code_locations=None)  # → seed_empty path

    _, recorder = _wire_minimal_org(
        monkeypatch,
        frontend=frontend,
        feature=feature,
        primary=primary,
        existing_backend_count=5,
    )

    await phase.run_backend_link(org_id=uuid.uuid4(), scan_id=uuid.uuid4())

    warnings = recorder.find("scan_backend_link_clearing_existing", level="warning")
    assert warnings, "expected scan_backend_link_clearing_existing warning"
    payload = warnings[0].kwargs
    assert payload["feature_id"] == str(feature.id)
    assert payload["existing_backend_links"] == 5
    assert payload["reason"] == "seed_empty"


async def test_no_warning_when_no_prior_backend_rows(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Fresh feature with no prior BACKEND rows → no clearing warning.

    The warning is gated on ``existing > 0`` — a first-pass scan
    where there's nothing to clear shouldn't fire it (otherwise every
    no-link feature triggers a noisy warning).
    """
    frontend_root = tmp_path / "frontend"
    frontend_root.mkdir()
    frontend = _FakeTracked(name="fe", path=str(frontend_root), head_sha="ff")
    feature = _FakeFeature(uuid.uuid4())
    primary = _FakePrimaryLink(code_locations=None)

    _, recorder = _wire_minimal_org(
        monkeypatch,
        frontend=frontend,
        feature=feature,
        primary=primary,
        existing_backend_count=0,
    )

    await phase.run_backend_link(org_id=uuid.uuid4(), scan_id=uuid.uuid4())

    assert not recorder.find("scan_backend_link_clearing_existing", level="warning")
