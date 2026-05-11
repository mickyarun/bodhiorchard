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

"""Tests for :mod:`app.services.job_repo_bulk_clone`.

The handler does three things — fan out clones, persist tracked repos,
kick off a scan — and these tests exercise each branch with the DB
+ git + GitHub layers stubbed out. Real Postgres / git / network
calls would all turn this into an integration test, which is out of
scope for this unit; the matching DB-integration coverage lives with
the route harness in the next phase.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
import structlog

from app.schemas.jobs import (
    BulkOnboardItemProgress,
    BulkOnboardItemState,
    BulkOnboardJobPayload,
    JobState,
)
from app.services import job_repo_bulk_clone, job_repo_bulk_clone_helpers
from app.services.job_repo_bulk_clone import handle_bulk_onboard_job
from app.services.repo_cloner import CloneResult

# ── Test doubles ───────────────────────────────────────────────────


class _FakeOrg:
    """Stand-in for ``Organization`` — only ``slug`` is read by the handler."""

    def __init__(self, *, slug: str = "acme") -> None:
        self.id: uuid.UUID = uuid.uuid4()
        self.slug = slug
        self.github_app_id = 12345
        self.github_app_private_key = "encrypted-pem"
        self.github_app_installation_id = 999
        self.github_app_slug = "acme-bodhi"


class _FakeOrgRepo:
    """Replaces ``OrganizationRepository`` to skip the DB layer entirely."""

    org: _FakeOrg | None = None

    def __init__(self, _db: Any) -> None:
        pass

    async def get_by_id(self, _id: uuid.UUID) -> _FakeOrg | None:
        return _FakeOrgRepo.org


class _FakeTrackedRepo:
    """Stand-in row returned by the fake :class:`_FakeTrackedRepoRepo`."""

    def __init__(self, *, path: str, name: str) -> None:
        self.id: uuid.UUID = uuid.uuid4()
        self.path = path
        self.name = name
        self.github_repo_full_name: str | None = None
        self.main_branch: str | None = None
        self.develop_branch: str | None = None
        self.uat_branch: str | None = None


class _FakeTrackedRepoRepo:
    """Replaces ``TrackedRepoRepository`` for the per-item upsert path."""

    upserts: list[tuple[str, str]] = []

    def __init__(self, _db: Any, *, org_id: uuid.UUID | None = None) -> None:
        self._org_id = org_id

    async def upsert(self, path: str, name: str) -> _FakeTrackedRepo:
        _FakeTrackedRepoRepo.upserts.append((path, name))
        return _FakeTrackedRepo(path=path, name=name)

    async def set_onboard_metadata(
        self,
        repo: _FakeTrackedRepo,
        *,
        github_full_name: str,
        main_branch: str,
        develop_branch: str | None,
        uat_branch: str | None,
    ) -> _FakeTrackedRepo:
        repo.github_repo_full_name = github_full_name
        repo.main_branch = main_branch
        repo.develop_branch = develop_branch
        repo.uat_branch = uat_branch or None
        return repo


class _FakeSession:
    """Stand-in for ``AsyncSession`` — flush / commit are no-ops."""

    async def __aenter__(self) -> _FakeSession:
        return self

    async def __aexit__(self, *_exc: Any) -> None:
        return None

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        return None

    async def refresh(self, _obj: Any) -> None:
        return None


def _fake_session_factory() -> _FakeSession:
    return _FakeSession()


# ── Job-queue capture ──────────────────────────────────────────────


class _UpdateRecorder:
    """Captures every ``update_job`` call so tests can inspect progress."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def __call__(self, _job_id: str, **kwargs: Any) -> None:
        self.calls.append(kwargs)


# ── Fixtures ───────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_globals() -> None:
    _FakeTrackedRepoRepo.upserts = []
    _FakeOrgRepo.org = _FakeOrg()


@pytest.fixture
def update_recorder(monkeypatch: pytest.MonkeyPatch) -> _UpdateRecorder:
    rec = _UpdateRecorder()
    monkeypatch.setattr(job_repo_bulk_clone, "update_job", rec)
    monkeypatch.setattr(job_repo_bulk_clone_helpers, "update_job", rec)
    return rec


@pytest.fixture
def patched_handler(monkeypatch: pytest.MonkeyPatch) -> None:
    """Wire all the test doubles into the handler + helpers modules."""
    monkeypatch.setattr(job_repo_bulk_clone, "OrganizationRepository", _FakeOrgRepo)
    monkeypatch.setattr(job_repo_bulk_clone_helpers, "TrackedRepoRepository", _FakeTrackedRepoRepo)

    async def _fake_token(_org: Any) -> str:
        return "ghs_TEST_TOKEN_VALUE"

    monkeypatch.setattr(job_repo_bulk_clone, "get_installation_token", _fake_token)


def _make_payload(*full_names: str) -> dict[str, Any]:
    items = [
        BulkOnboardItemProgress(
            full_name=fn,
            main_branch="main",
            develop_branch="develop",
            uat_branch=None,
            status=BulkOnboardItemState.PENDING,
        )
        for fn in full_names
    ]
    payload = BulkOnboardJobPayload(org_id=uuid.uuid4(), items=items)
    return payload.model_dump(mode="json")


# ── Tests ──────────────────────────────────────────────────────────


def _patch_kickoff(
    monkeypatch: pytest.MonkeyPatch,
    *,
    scan_id: uuid.UUID | None = None,
    warning: str | None = None,
    raises: BaseException | None = None,
    capture: list[dict[str, Any]] | None = None,
) -> None:
    """Replace ``kick_off_onboard_scan`` in the bulk-onboard module.

    Either returns ``(scan_id, warning)`` or raises ``raises``. When
    ``capture`` is provided, every invocation's kwargs are appended to it.
    """

    async def _fake(**kwargs: Any) -> tuple[uuid.UUID | None, str | None]:
        if capture is not None:
            capture.append(kwargs)
        if raises is not None:
            raise raises
        return scan_id, warning

    monkeypatch.setattr(job_repo_bulk_clone, "kick_off_onboard_scan", _fake)


@pytest.mark.asyncio
async def test_bulk_onboard_three_repos_one_fails(
    monkeypatch: pytest.MonkeyPatch,
    update_recorder: _UpdateRecorder,
    patched_handler: None,
) -> None:
    """Two repos clone, one fails. Only the two succeeders reach the kickoff."""

    async def _fake_clone(*, url: str, org_slug: str, branch: str | None = None) -> CloneResult:
        assert "x-access-token:ghs_TEST_TOKEN_VALUE@github.com" in url
        assert org_slug == "acme"
        if "broken" in url:
            return CloneResult(success=False, error="Boom!")
        # Synthesize a path from the URL's tail.
        repo_name = url.rstrip(".git").rsplit("/", 1)[-1]
        return CloneResult(
            success=True,
            path=f"/tmp/repos/acme/{repo_name}",
            default_branch="main",
        )

    kickoff_calls: list[dict[str, Any]] = []
    expected_scan = uuid.uuid4()
    monkeypatch.setattr(job_repo_bulk_clone_helpers, "clone_or_update", _fake_clone)
    monkeypatch.setattr(job_repo_bulk_clone, "AsyncSessionLocal", _fake_session_factory)
    _patch_kickoff(monkeypatch, scan_id=expected_scan, capture=kickoff_calls)

    payload = _make_payload("acme/widgets", "acme/broken", "acme/gizmos")
    await handle_bulk_onboard_job("job-123", payload)

    # Kickoff called exactly once with the two surviving repo_ids.
    assert len(kickoff_calls) == 1
    assert len(kickoff_calls[0]["repo_ids"]) == 2

    # Final update marks the job complete and contains the summary lists.
    completed = [c for c in update_recorder.calls if c.get("state") is JobState.COMPLETED]
    assert len(completed) == 1
    final_result = completed[0]["result"]
    assert sorted(final_result["succeeded"]) == ["acme/gizmos", "acme/widgets"]
    assert [f["full_name"] for f in final_result["failed"]] == ["acme/broken"]
    assert final_result["scan_id"] == str(expected_scan)

    # Per-item progress crossed every state.
    statuses_seen: set[str] = set()
    for call in update_recorder.calls:
        result = call.get("result")
        if isinstance(result, dict) and "items" in result:
            for it in result["items"]:
                statuses_seen.add(it["status"])
    assert {"pending", "cloning", "done", "error"} <= statuses_seen


@pytest.mark.asyncio
async def test_bulk_onboard_all_fail_no_scan(
    monkeypatch: pytest.MonkeyPatch,
    update_recorder: _UpdateRecorder,
    patched_handler: None,
) -> None:
    """If every clone fails, the kickoff is never invoked."""

    async def _fake_clone(*, url: str, org_slug: str, branch: str | None = None) -> CloneResult:
        _ = url, org_slug
        return CloneResult(success=False, error="Permission denied")

    kickoff_calls: list[dict[str, Any]] = []
    monkeypatch.setattr(job_repo_bulk_clone_helpers, "clone_or_update", _fake_clone)
    monkeypatch.setattr(job_repo_bulk_clone, "AsyncSessionLocal", _fake_session_factory)
    _patch_kickoff(monkeypatch, scan_id=uuid.uuid4(), capture=kickoff_calls)

    payload = _make_payload("acme/a", "acme/b")
    await handle_bulk_onboard_job("job-456", payload)

    assert kickoff_calls == []
    completed = [c for c in update_recorder.calls if c.get("state") is JobState.COMPLETED]
    assert len(completed) == 1
    final_result = completed[0]["result"]
    assert final_result["succeeded"] == []
    assert final_result["scan_id"] is None
    assert len(final_result["failed"]) == 2


@pytest.mark.asyncio
async def test_bulk_onboard_token_never_logged(
    monkeypatch: pytest.MonkeyPatch,
    update_recorder: _UpdateRecorder,
    patched_handler: None,
) -> None:
    """Even when clone errors echo the URL, the raw token never reaches logs."""
    log_entries: list[dict[str, Any]] = []

    def _capture(_logger: Any, _method: str, event_dict: dict[str, Any]) -> str:
        log_entries.append(dict(event_dict))
        # Returning a string short-circuits to the stdlib renderer below.
        return str(event_dict)

    structlog.configure(processors=[_capture])

    async def _fake_clone(*, url: str, org_slug: str, branch: str | None = None) -> CloneResult:
        # Simulate git echoing the auth URL (worst case for token leak).
        return CloneResult(success=False, error=f"fatal: cannot fetch {url}")

    monkeypatch.setattr(job_repo_bulk_clone_helpers, "clone_or_update", _fake_clone)
    monkeypatch.setattr(job_repo_bulk_clone, "AsyncSessionLocal", _fake_session_factory)
    _patch_kickoff(monkeypatch, scan_id=uuid.uuid4())

    payload = _make_payload("acme/secrets")
    await handle_bulk_onboard_job("job-789", payload)

    serialised_logs = repr(log_entries)
    assert "ghs_TEST_TOKEN_VALUE" not in serialised_logs
    # Sanity-check: the call definitely went through the failure path.
    final_result = next(
        c["result"] for c in update_recorder.calls if c.get("state") is JobState.COMPLETED
    )
    assert final_result["failed"]
    # Confirm the per-item error was sanitised.
    err_text = final_result["failed"][0]["error"]
    assert "ghs_TEST_TOKEN_VALUE" not in err_text


@pytest.mark.asyncio
async def test_bulk_onboard_kicks_one_scan(
    monkeypatch: pytest.MonkeyPatch,
    update_recorder: _UpdateRecorder,
    patched_handler: None,
) -> None:
    """N successful clones produce a single kickoff call covering every repo_id."""

    async def _fake_clone(*, url: str, org_slug: str, branch: str | None = None) -> CloneResult:
        _ = org_slug
        repo_name = url.rstrip(".git").rsplit("/", 1)[-1]
        return CloneResult(
            success=True,
            path=f"/tmp/repos/acme/{repo_name}",
            default_branch="main",
        )

    expected_scan = uuid.uuid4()
    kickoff_calls: list[dict[str, Any]] = []
    monkeypatch.setattr(job_repo_bulk_clone_helpers, "clone_or_update", _fake_clone)
    monkeypatch.setattr(job_repo_bulk_clone, "AsyncSessionLocal", _fake_session_factory)
    _patch_kickoff(monkeypatch, scan_id=expected_scan, capture=kickoff_calls)

    payload = _make_payload(*[f"acme/repo-{i:02d}" for i in range(12)])
    await handle_bulk_onboard_job("job-batch", payload)

    # Exactly one kickoff, all 12 repo_ids in a single call — no chunking.
    assert len(kickoff_calls) == 1
    assert len(kickoff_calls[0]["repo_ids"]) == 12

    completed = [c for c in update_recorder.calls if c.get("state") is JobState.COMPLETED]
    assert len(completed) == 1
    final_result = completed[0]["result"]
    assert final_result["scan_id"] == str(expected_scan)


@pytest.mark.asyncio
async def test_bulk_onboard_active_scan_fails_job(
    monkeypatch: pytest.MonkeyPatch,
    update_recorder: _UpdateRecorder,
    patched_handler: None,
) -> None:
    """ScanAlreadyActiveError → job FAILED with a friendly message, no traceback."""
    from app.services.scan.runner import ScanAlreadyActiveError

    async def _fake_clone(*, url: str, org_slug: str, branch: str | None = None) -> CloneResult:
        _ = org_slug
        repo_name = url.rstrip(".git").rsplit("/", 1)[-1]
        return CloneResult(
            success=True,
            path=f"/tmp/repos/acme/{repo_name}",
            default_branch="main",
        )

    monkeypatch.setattr(job_repo_bulk_clone_helpers, "clone_or_update", _fake_clone)
    monkeypatch.setattr(job_repo_bulk_clone, "AsyncSessionLocal", _fake_session_factory)
    _patch_kickoff(
        monkeypatch,
        raises=ScanAlreadyActiveError(scan_id=uuid.uuid4(), status="pushing_setup"),
    )

    payload = _make_payload("acme/one", "acme/two")
    await handle_bulk_onboard_job("job-active", payload)

    failed = [c for c in update_recorder.calls if c.get("state") is JobState.FAILED]
    assert len(failed) == 1
    # User-friendly message, not a stack trace.
    assert "Another scan is already running" in (failed[0].get("error") or "")
    assert "Traceback" not in (failed[0].get("error") or "")


@pytest.mark.asyncio
async def test_bulk_onboard_embedding_warning_completes_job(
    monkeypatch: pytest.MonkeyPatch,
    update_recorder: _UpdateRecorder,
    patched_handler: None,
) -> None:
    """Embedding-down warning surfaces in status_message, job still COMPLETED."""

    async def _fake_clone(*, url: str, org_slug: str, branch: str | None = None) -> CloneResult:
        _ = org_slug
        repo_name = url.rstrip(".git").rsplit("/", 1)[-1]
        return CloneResult(
            success=True,
            path=f"/tmp/repos/acme/{repo_name}",
            default_branch="main",
        )

    monkeypatch.setattr(job_repo_bulk_clone_helpers, "clone_or_update", _fake_clone)
    monkeypatch.setattr(job_repo_bulk_clone, "AsyncSessionLocal", _fake_session_factory)
    _patch_kickoff(monkeypatch, scan_id=None, warning="Embedding service unavailable.")

    payload = _make_payload("acme/widgets")
    await handle_bulk_onboard_job("job-embed", payload)

    completed = [c for c in update_recorder.calls if c.get("state") is JobState.COMPLETED]
    assert len(completed) == 1
    assert "Embedding service unavailable" in (completed[0].get("status_message") or "")
    assert completed[0]["result"]["scan_id"] is None
