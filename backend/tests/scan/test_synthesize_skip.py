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

"""Tests for the skip-vs-run decision in ``synthesize.run``.

The earlier wipe-then-resynth orchestration was retired in favour of the
incremental-CRUD model: the synthesise stage now stages new writes via
the accumulator and ``feature_reconciler`` decides per-row whether each
existing feature is updated, revived, inactivated, or kept (see
``app.services.feature_reconciler``).

What still matters at the orchestration layer is the cheap-path early
return when the SHA-skip predicate says "nothing changed" — that's the
only check between an unchanged scan and a costly Claude call.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import Any

import pytest

from app.services.scan.stages import StageContext
from app.services.scan.stages import synthesize as stage
from app.services.scan.stages._skip_predicates import SkipDecision


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


def _patch_runtime_context(monkeypatch: pytest.MonkeyPatch, org_id: uuid.UUID) -> None:
    """Make ``resolve_runtime_context`` return a populated context (no real session)."""

    class _V2:
        def __init__(self, oid: uuid.UUID) -> None:
            self.org_id = oid
            self.scan_id = uuid.uuid4()

    monkeypatch.setattr(stage, "resolve_runtime_context", lambda _config: _V2(org_id))


async def test_skip_short_circuits_when_sha_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SHA unchanged (skip=True) → stage MUST return early without running synthesis.

    The early-return is the entire reason the skip predicate exists; if it
    falls through, every unchanged scan re-runs Claude at full cost.
    """
    org_id = uuid.uuid4()
    repo_id = uuid.uuid4()
    fake_session = _FakeSession()

    _patch_runtime_context(monkeypatch, org_id)
    _patch_session(monkeypatch, fake_session)

    async def _skip(_db: Any, **_kw: Any) -> SkipDecision:
        return SkipDecision(skip=True, reason="head_sha unchanged: deadbeef", head_sha="deadbeef")

    monkeypatch.setattr(stage, "should_skip_feature_synthesis", _skip)

    config = {"repo_id": str(repo_id)}
    out = await stage.run(StageContext(run_id="r", repo_path="/x", repo_name="r"), [], config)

    # No commit needed on the skip path — nothing was written.
    assert fake_session.committed is False
    # The skip path renders a SkipDecision-shaped StageOutput.
    assert out.extras.get("skipped_unchanged") is True
