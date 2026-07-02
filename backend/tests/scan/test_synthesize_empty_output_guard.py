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

"""Tests for the synthesis-produced-zero-features guard in ``synthesize.run``.

Regression test for the 2026-05-26 incident: PR-merge dispatch escalated
to full scan, the soft-delete prelude flagged 17 features for revival,
then the Claude subprocess exited with returncode 0 and empty stdout
(Anthropic Tools API rejected a malformed input_schema → no MCP tools
registered → no ``write_synthesis_feature`` calls produced). With
``outcome.success`` true and reconcile counts all zero, the orchestrator
treated the run as success and never rolled back the soft-delete.

The guard now raises when the reconciler persisted nothing despite
non-empty community input, which lets ``_run_one`` restore this repo's
soft-deleted slice via ``rollback_soft_deleted_for_repo``.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import Any

import pytest

from app.models.organization import AIProvider
from app.schemas.scan import Community
from app.services.scan.stages import StageContext
from app.services.scan.stages import synthesize as stage
from app.services.scan.stages._skip_predicates import SkipDecision


def _make_community(label: str = "x") -> Community:
    """Build a minimal Community matching the post-reduce shape callers pass.

    The synthesis stage's prompt builder reads ``label``, ``drop_reason``,
    ``files``, and ``source_community_ids``. Defaulting the rest keeps
    tests focused on the guard logic rather than community plumbing.
    """
    return Community(
        label=label,
        files=[f"src/{label}.ts"],
        source_community_ids=["c0"],
        community_id="",
    )


class _FakeSession:
    """Minimal AsyncSession stand-in: tracks commits, ignores reads."""

    def __init__(self) -> None:
        self.committed = False

    async def commit(self) -> None:
        self.committed = True


class _FakeOutcome:
    """Engine outcome matching the duck-typed shape used by ``stage.run``."""

    def __init__(self, success: bool) -> None:
        self.success = success
        self.input_tokens: int | None = None
        self.output_tokens: int | None = None
        self.cost_usd: float = 0.0
        self.error: str | None = None


class _FakeEngine:
    async def run(self, _request: Any) -> _FakeOutcome:
        # Mirror the production-failure shape: subprocess exited cleanly
        # but emitted zero tool calls.
        return _FakeOutcome(success=True)


def _patch_session(monkeypatch: pytest.MonkeyPatch, session: _FakeSession) -> None:
    @asynccontextmanager
    async def _cm(_org_id: uuid.UUID) -> Any:
        yield session

    monkeypatch.setattr(stage, "with_session", _cm)


def _patch_runtime_context(monkeypatch: pytest.MonkeyPatch, org_id: uuid.UUID) -> None:
    class _Runtime:
        def __init__(self, oid: uuid.UUID) -> None:
            self.org_id = oid
            self.scan_id = uuid.uuid4()

    monkeypatch.setattr(stage, "resolve_runtime_context", lambda _config: _Runtime(org_id))


def _patch_no_skip(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _no_skip(_db: Any, **_kw: Any) -> SkipDecision:
        return SkipDecision(skip=False, reason="", head_sha="cafebabe")

    monkeypatch.setattr(stage, "should_skip_feature_synthesis", _no_skip)


def _patch_origin_refresh(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub the pre-spawn token refresh so the test never hits the DB.

    ``stage.run`` re-stamps ``origin`` with a fresh installation token
    before spawning the synthesis subprocess. The real helper opens an
    ``AsyncSessionLocal`` + queries ``tracked_repositories`` — neither
    exists in these unit-test paths, so we stub it to a no-op.
    """

    async def _noop(*, working_dir: str, org_id: uuid.UUID) -> bool:
        return False

    monkeypatch.setattr(stage, "refresh_origin_token_for_spawn", _noop)


def _patch_org_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub the org load so it doesn't touch the fake session.

    ``stage.run`` now loads the org to route synthesis through its
    provider. These tests mock the engine, so the org's value is never
    read — the stub just returns a Claude-default org without a real DB.
    """

    class _FakeOrg:
        ai_provider = AIProvider.claude

    class _FakeOrgRepo:
        def __init__(self, _db: Any) -> None: ...

        async def get_by_id(self, _entity_id: uuid.UUID) -> _FakeOrg:
            return _FakeOrg()

    monkeypatch.setattr(stage, "OrganizationRepository", _FakeOrgRepo)


async def test_raises_when_reconcile_persists_zero_for_nonempty_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reconcile reports 0 inserted/updated/revived AND communities is non-empty.

    This is the exact silent-failure shape: synthesis subprocess
    succeeded but emitted no features, so the reconciler had nothing
    to match. The guard MUST raise so ``_run_one`` can roll back the
    soft-delete; without the raise, the orchestrator treats the run
    as success and leaves the org with a wholesale feature loss.
    """
    org_id = uuid.uuid4()
    repo_id = uuid.uuid4()
    fake_session = _FakeSession()

    _patch_runtime_context(monkeypatch, org_id)
    _patch_session(monkeypatch, fake_session)
    _patch_no_skip(monkeypatch)
    _patch_origin_refresh(monkeypatch)
    _patch_org_repo(monkeypatch)
    monkeypatch.setattr(stage, "_resolve_engine", lambda _config: _FakeEngine())

    async def _reset_progress(_a: Any, _b: Any) -> None: ...

    monkeypatch.setattr(stage, "reset_tool_progress", lambda _a, _b: None)
    monkeypatch.setattr(stage, "reset_tool_progress_for_org", lambda _a: None)
    monkeypatch.setattr(stage, "reset_for_org", lambda _a: None)

    # Pin reconcile + count to the empty-output shape.
    async def _zero_reconcile(_config: dict[str, Any], *, repo_id: uuid.UUID) -> dict[str, Any]:
        return {
            "reconcile_inserted": 0,
            "reconcile_updated": 0,
            "reconcile_revived": 0,
            "reconcile_inactivated": 0,
            "reconcile_match_strategies": {},
        }

    async def _zero_count(_config: dict[str, Any]) -> int:
        return 0

    monkeypatch.setattr(stage, "_reconcile_synthesised_batch", _zero_reconcile)
    monkeypatch.setattr(stage, "_count_synthesized_features", _zero_count)

    config = {
        "repo_id": str(repo_id),
        "mcp_backend_url": "http://localhost:8000",
        "mcp_token": "test-token",
    }
    communities = [_make_community()]

    with pytest.raises(RuntimeError, match=r"0 features from 1 communities"):
        await stage.run(
            StageContext(run_id="r", repo_path="/x", repo_name="r"), communities, config
        )


async def test_no_raise_when_reconcile_persisted_anything(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One inserted, updated, or revived → guard stays silent.

    The guard is a silent-zero detector; any non-zero reconcile
    activity means synthesis emitted real work, so the stage should
    return normally even if the *active count* later happens to be
    zero for unrelated reasons.
    """
    org_id = uuid.uuid4()
    repo_id = uuid.uuid4()
    fake_session = _FakeSession()

    _patch_runtime_context(monkeypatch, org_id)
    _patch_session(monkeypatch, fake_session)
    _patch_no_skip(monkeypatch)
    _patch_origin_refresh(monkeypatch)
    _patch_org_repo(monkeypatch)
    monkeypatch.setattr(stage, "_resolve_engine", lambda _config: _FakeEngine())
    monkeypatch.setattr(stage, "reset_tool_progress", lambda _a, _b: None)
    monkeypatch.setattr(stage, "reset_tool_progress_for_org", lambda _a: None)
    monkeypatch.setattr(stage, "reset_for_org", lambda _a: None)

    async def _one_inserted(_config: dict[str, Any], *, repo_id: uuid.UUID) -> dict[str, Any]:
        return {
            "reconcile_inserted": 1,
            "reconcile_updated": 0,
            "reconcile_revived": 0,
            "reconcile_inactivated": 0,
            "reconcile_match_strategies": {"signature": 1},
        }

    async def _one_count(_config: dict[str, Any]) -> int:
        return 1

    async def _no_audit(_config: dict[str, Any]) -> int:
        return 0

    monkeypatch.setattr(stage, "_reconcile_synthesised_batch", _one_inserted)
    monkeypatch.setattr(stage, "_count_synthesized_features", _one_count)
    monkeypatch.setattr(stage, "_run_coverage_audit", _no_audit)

    config = {
        "repo_id": str(repo_id),
        "mcp_backend_url": "http://localhost:8000",
        "mcp_token": "test-token",
    }
    communities = [_make_community()]

    out = await stage.run(
        StageContext(run_id="r", repo_path="/x", repo_name="r"), communities, config
    )
    assert out.extras.get("empty_output_guard_tripped") is None
    assert out.extras.get("features_synthesized") == 1


async def test_no_raise_when_communities_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Empty community input → guard MUST NOT fire.

    An empty community list is a legitimate "nothing to synthesise"
    state (e.g., infra-only PR where the filter dropped everything);
    raising here would block valid clean scans.
    """
    org_id = uuid.uuid4()
    repo_id = uuid.uuid4()
    fake_session = _FakeSession()

    _patch_runtime_context(monkeypatch, org_id)
    _patch_session(monkeypatch, fake_session)
    _patch_no_skip(monkeypatch)
    _patch_origin_refresh(monkeypatch)
    monkeypatch.setattr(stage, "_resolve_engine", lambda _config: _FakeEngine())
    monkeypatch.setattr(stage, "reset_tool_progress", lambda _a, _b: None)
    monkeypatch.setattr(stage, "reset_tool_progress_for_org", lambda _a: None)
    monkeypatch.setattr(stage, "reset_for_org", lambda _a: None)

    async def _zero_reconcile(_config: dict[str, Any], *, repo_id: uuid.UUID) -> dict[str, Any]:
        return {
            "reconcile_inserted": 0,
            "reconcile_updated": 0,
            "reconcile_revived": 0,
            "reconcile_inactivated": 0,
            "reconcile_match_strategies": {},
        }

    async def _zero_count(_config: dict[str, Any]) -> int:
        return 0

    async def _no_audit(_config: dict[str, Any]) -> int:
        return 0

    monkeypatch.setattr(stage, "_reconcile_synthesised_batch", _zero_reconcile)
    monkeypatch.setattr(stage, "_count_synthesized_features", _zero_count)
    monkeypatch.setattr(stage, "_run_coverage_audit", _no_audit)

    config = {
        "repo_id": str(repo_id),
        "mcp_backend_url": "http://localhost:8000",
        "mcp_token": "test-token",
    }

    out = await stage.run(StageContext(run_id="r", repo_path="/x", repo_name="r"), [], config)
    assert out.extras.get("empty_output_guard_tripped") is None
