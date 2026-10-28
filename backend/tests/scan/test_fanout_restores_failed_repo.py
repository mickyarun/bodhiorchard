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

"""A repo run that fails before synthesis finishes must get its soft-deleted features back.

The workflow catches a failing stage (e.g. synthesis writing zero features),
marks the run FAILED and returns normally, so the fanout only learns about
the failure from the returned run's status. Before the fix only an exception
escaping ``start_run`` triggered the restore, which never happens for a stage
failure: a failed rescan left every feature of the repo deactivated. A stage
failing *after* synthesis must not restore: the reconciler has already
settled the features, and reviving the old slice would bring back features
for code that was removed.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest

from app.schemas.scan import RunConfig, TestRun
from app.services.scan import runner_fanout
from app.services.scan.setup import RepoDescriptor

REPO_ID = uuid.uuid4()
FEATURE_IDS = [uuid.uuid4(), uuid.uuid4()]


class _Observer:
    """Records the failure the fanout reports for a repo."""

    failures: list[str] = []

    def __init__(self, **_: Any) -> None:
        pass

    async def on_run_failed(self, *, error: str) -> None:
        self.failures.append(error)


async def _noop(**_: Any) -> None:
    return None


def _wire(
    monkeypatch: pytest.MonkeyPatch, run_status: str | None, completed: list[str] | None = None
) -> list[dict[str, Any]]:
    """Stub the fanout's collaborators; return the restore calls it makes."""
    restored: list[dict[str, Any]] = []
    _Observer.failures = []

    async def soft_delete(**_: Any) -> dict[uuid.UUID, list[uuid.UUID]]:
        return {REPO_ID: list(FEATURE_IDS)}

    async def restore(**kwargs: Any) -> None:
        restored.append(kwargs)

    async def start_run(**kwargs: Any) -> TestRun:
        if run_status is None:
            raise RuntimeError("indexer crashed")
        return TestRun(
            run_id="r1",
            repo_name="shop",
            repo_path="/tmp/shop",
            config=kwargs["config"],
            status=run_status,
            started_at=datetime.now(UTC),
            error="synthesis produced 0 features" if run_status == "failed" else None,
            completed_stages=list(completed or ["repo_setup", "ingest"]),
        )

    async def scan_cfg(_org: uuid.UUID) -> dict[str, Any]:
        return {}

    async def no_paths(**_: Any) -> list[str]:
        return []

    monkeypatch.setattr(runner_fanout, "soft_delete_changed_repos", soft_delete)
    monkeypatch.setattr(runner_fanout, "rollback_soft_deleted_for_repo", restore)
    monkeypatch.setattr(runner_fanout, "start_run", start_run)
    monkeypatch.setattr(runner_fanout, "mint_mcp_credentials", lambda **_: {})
    monkeypatch.setattr(runner_fanout, "load_scan_cfg", scan_cfg)
    monkeypatch.setattr(runner_fanout, "DBTimelineObserver", _Observer)
    monkeypatch.setattr(runner_fanout, "run_global_phases", _noop)
    monkeypatch.setattr(runner_fanout, "_mark_scan_terminal", _noop)
    monkeypatch.setattr(runner_fanout, "_load_all_repo_paths_for_scan", no_paths)
    return restored


async def _scan() -> None:
    descriptor = RepoDescriptor(
        repo_id=REPO_ID, repo_path="/tmp/shop", repo_name="shop", main_branch="main", head_sha=None
    )
    await runner_fanout._execute_scan(
        org_id=uuid.uuid4(),
        scan_id=uuid.uuid4(),
        repo_descriptors=[descriptor],
        config=RunConfig(),
    )


async def test_failed_run_restores_the_repos_soft_deleted_features(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    restored = _wire(monkeypatch, "failed")

    await _scan()

    assert len(restored) == 1
    assert restored[0]["repo_id"] == REPO_ID
    assert restored[0]["feature_ids"] == FEATURE_IDS
    assert _Observer.failures == []


async def test_failure_after_synthesis_keeps_the_reconciled_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    restored = _wire(monkeypatch, "failed", ["ingest", "synthesize", "extract_routes"])

    await _scan()

    assert restored == []


async def test_successful_run_keeps_the_soft_delete(monkeypatch: pytest.MonkeyPatch) -> None:
    restored = _wire(monkeypatch, "done")

    await _scan()

    assert restored == []


async def test_exception_out_of_the_workflow_still_restores(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    restored = _wire(monkeypatch, None)

    await _scan()

    assert [r["feature_ids"] for r in restored] == [FEATURE_IDS]
    assert _Observer.failures == ["RuntimeError: indexer crashed"]
