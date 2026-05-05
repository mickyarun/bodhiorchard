# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Tests for the wipe-then-resynth orchestration in ``synthesize.run``.

The actual SQL semantics of the wipe (cascade, partial unique on PRIMARY)
live in the alembic migration + the SQLAlchemy model and are exercised
end-to-end by ``alembic upgrade head`` against the dev DB. These tests
are scoped to the orchestration: when does the synthesise stage call the
wipe, and when does it skip it?
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import Any

import pytest

from app.services.scan.stages import StageContext
from app.services.scan.stages import synthesize as stage
from app.services.scan.stages._skip_predicates import SkipDecision


class _FakeRepo:
    """Stand-in for :class:`FeatureRepository` recording wipe calls."""

    def __init__(self) -> None:
        self.deleted: list[uuid.UUID] = []

    async def delete_for_primary_repo(self, repo_id: uuid.UUID) -> int:
        self.deleted.append(repo_id)
        return 7


class _FakeSession:
    def __init__(self) -> None:
        self.committed = False

    async def commit(self) -> None:
        self.committed = True


def _patch_session(monkeypatch: pytest.MonkeyPatch, session: _FakeSession) -> None:
    """Replace ``with_session`` with a context manager yielding ``session``."""

    @asynccontextmanager
    async def _cm(_org_id: uuid.UUID) -> Any:
        yield session

    monkeypatch.setattr(stage, "with_session", _cm)


def _patch_v2_context(monkeypatch: pytest.MonkeyPatch, org_id: uuid.UUID) -> None:
    """Make ``resolve_v2_context`` return a populated context (no real session)."""

    class _V2:
        def __init__(self, oid: uuid.UUID) -> None:
            self.org_id = oid
            self.scan_id = uuid.uuid4()

    monkeypatch.setattr(stage, "resolve_v2_context", lambda _config: _V2(org_id))


async def test_wipe_runs_when_skip_predicate_returns_no_skip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SHA changed (skip=False) → wipe MUST run before synthesis fan-out.

    Without the wipe, the partial unique index on (repo_id, feature_title)
    would trip on the second scan as a new "Feature: X" insert collides
    with the prior scan's row.
    """
    org_id = uuid.uuid4()
    repo_id = uuid.uuid4()
    fake_repo = _FakeRepo()
    fake_session = _FakeSession()

    _patch_v2_context(monkeypatch, org_id)
    _patch_session(monkeypatch, fake_session)
    monkeypatch.setattr(
        stage,
        "FeatureRepository",
        lambda _db, *, org_id: fake_repo,  # noqa: ARG005
    )

    async def _no_skip(_db: Any, **_kw: Any) -> SkipDecision:
        return SkipDecision(skip=False, reason="head_sha changed")

    monkeypatch.setattr(stage, "should_skip_feature_synthesis", _no_skip)

    # mcp_credentials_missing branch returns early with skipped_cache=True;
    # the wipe MUST already have happened at that point.
    config = {"v2_repo_id": str(repo_id)}
    out = await stage.run(StageContext(run_id="r", repo_path="/x", repo_name="r"), [], config)

    assert fake_repo.deleted == [repo_id]
    assert fake_session.committed is True
    # Stage proceeds past the wipe — proves the wipe completed before the
    # skip-cache branch was entered (no input → "no input" reason).
    assert out.extras.get("reason") in ("no input", "mcp_credentials_missing")


async def test_wipe_skipped_when_skip_predicate_returns_skip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SHA unchanged (skip=True) → wipe MUST NOT run; existing rows survive."""
    org_id = uuid.uuid4()
    repo_id = uuid.uuid4()
    fake_repo = _FakeRepo()
    fake_session = _FakeSession()

    _patch_v2_context(monkeypatch, org_id)
    _patch_session(monkeypatch, fake_session)
    monkeypatch.setattr(
        stage,
        "FeatureRepository",
        lambda _db, *, org_id: fake_repo,  # noqa: ARG005
    )

    async def _skip(_db: Any, **_kw: Any) -> SkipDecision:
        return SkipDecision(skip=True, reason="head_sha unchanged: deadbeef", head_sha="deadbeef")

    monkeypatch.setattr(stage, "should_skip_feature_synthesis", _skip)

    config = {"v2_repo_id": str(repo_id)}
    out = await stage.run(StageContext(run_id="r", repo_path="/x", repo_name="r"), [], config)

    assert fake_repo.deleted == []
    assert fake_session.committed is False
    # The skip path renders a SkipDecision-shaped StageOutput.
    assert out.extras.get("skipped_unchanged") is True


async def test_wipe_failure_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    """A wipe error MUST raise — synthesis depends on the post-condition.

    Silently continuing past a failed wipe would leave stale rows and
    trip the partial unique index unpredictably mid-run.
    """
    org_id = uuid.uuid4()
    repo_id = uuid.uuid4()
    fake_session = _FakeSession()

    _patch_v2_context(monkeypatch, org_id)
    _patch_session(monkeypatch, fake_session)

    class _BoomRepo:
        async def delete_for_primary_repo(self, _repo_id: uuid.UUID) -> int:
            raise RuntimeError("simulated DB outage")

    monkeypatch.setattr(
        stage,
        "FeatureRepository",
        lambda _db, *, org_id: _BoomRepo(),  # noqa: ARG005
    )

    async def _no_skip(_db: Any, **_kw: Any) -> SkipDecision:
        return SkipDecision(skip=False)

    monkeypatch.setattr(stage, "should_skip_feature_synthesis", _no_skip)

    config = {"v2_repo_id": str(repo_id)}
    with pytest.raises(RuntimeError, match="simulated DB outage"):
        await stage.run(
            StageContext(run_id="r", repo_path="/x", repo_name="r"),
            [],
            config,
        )
