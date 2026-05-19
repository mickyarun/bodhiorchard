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

"""Tests for :func:`enqueue_rescan_delivery`.

Verifies the synthetic delivery shape, error propagation, and that the
helper actually publishes onto the per-(org, repo) Redis stream — the
PR-merge consumer's contract assumes ``event_type='repo_scan'`` rows
look exactly like ``pull_request`` rows below the field level.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import Any

import pytest

from app.services.scan import rescan_enqueue as mod


class _FakeRepoRow:
    def __init__(self) -> None:
        self.path = "/tmp/fakerepo"
        self.head_sha = "BASE_SHA_FROM_TRACKED"
        self.main_branch = "main"
        self.name = "owner/fakerepo"


class _FakeTrackedRepoRepo:
    """Returns a fixed repo row regardless of id; ``find_missing`` flag
    flips it to return ``None`` to drive the not-found branch.
    """

    repo: _FakeRepoRow | None = _FakeRepoRow()

    def __init__(self, *_a: Any, **_kw: Any) -> None:
        pass

    async def get_by_id(self, _repo_id: uuid.UUID) -> _FakeRepoRow | None:
        return self.repo


class _FakeWebhookLogRepo:
    """Captures the kwargs passed to :meth:`record_replay_row`."""

    last_call: dict[str, Any] = {}
    inserted: bool = True

    def __init__(self, *_a: Any, **_kw: Any) -> None:
        pass

    async def record_replay_row(
        self,
        *,
        delivery_id: str,
        event_type: str,
        org_id: uuid.UUID,
        repo_id: uuid.UUID | None,
        payload: dict[str, Any],
        payload_summary: dict[str, Any] | None = None,
    ) -> bool:
        _FakeWebhookLogRepo.last_call = {
            "delivery_id": delivery_id,
            "event_type": event_type,
            "org_id": org_id,
            "repo_id": repo_id,
            "payload": payload,
            "payload_summary": payload_summary,
        }
        return _FakeWebhookLogRepo.inserted


@pytest.fixture(autouse=True)
def _reset_captures() -> None:
    _FakeTrackedRepoRepo.repo = _FakeRepoRow()
    _FakeWebhookLogRepo.last_call = {}
    _FakeWebhookLogRepo.inserted = True


@pytest.fixture
def _patched(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    captured: dict[str, Any] = {
        "publish_calls": [],
        "ls_remote_result": ("REMOTE_HEAD_SHA\trefs/heads/main\n", "", 0),
    }

    @asynccontextmanager
    async def _fake_session(_org_id: uuid.UUID) -> Any:
        yield _FakeDb()

    async def _fake_run_git(args: list[str], cwd: str, **_kw: Any) -> tuple[str, str, int]:
        assert args[0] == "ls-remote"
        return captured["ls_remote_result"]

    async def _fake_publish(*, org_id: uuid.UUID, repo_id: uuid.UUID, delivery_id: str) -> bool:
        captured["publish_calls"].append(
            {"org_id": org_id, "repo_id": repo_id, "delivery_id": delivery_id}
        )
        return True

    async def _fake_detect_main(_repo_path: str) -> str | None:
        return "main"

    monkeypatch.setattr(mod, "with_session", _fake_session)
    monkeypatch.setattr(mod, "TrackedRepoRepository", _FakeTrackedRepoRepo)
    monkeypatch.setattr(mod, "WebhookLogRepository", _FakeWebhookLogRepo)
    monkeypatch.setattr(mod, "run_git", _fake_run_git)
    monkeypatch.setattr(mod, "publish_pr_merge_delivery", _fake_publish)
    monkeypatch.setattr(mod, "_detect_main_branch", _fake_detect_main)
    return captured


class _FakeDb:
    """Minimal AsyncSession stand-in covering only what the helper touches."""

    async def commit(self) -> None:
        return None


async def test_happy_path_publishes_and_returns_delivery_id(
    _patched: dict[str, Any],
) -> None:
    """End-to-end: helper resolves head SHA, inserts replay row, XADDs."""
    org_id = uuid.uuid4()
    repo_id = uuid.uuid4()

    delivery_id = await mod.enqueue_rescan_delivery(org_id=org_id, repo_id=repo_id)

    assert delivery_id.startswith("rescan-")
    assert len(_patched["publish_calls"]) == 1
    assert _patched["publish_calls"][0]["delivery_id"] == delivery_id
    assert _patched["publish_calls"][0]["org_id"] == org_id
    assert _patched["publish_calls"][0]["repo_id"] == repo_id


async def test_payload_shape_matches_pr_merge_dispatcher_contract(
    _patched: dict[str, Any],
) -> None:
    """The replay payload must carry the exact fields the dispatcher reads.

    handle_pr_merge_delivery → ``payload["pr_number"]``, ``base_sha``,
    ``head_sha``, ``full_name``. Any change here is a contract break.
    """
    await mod.enqueue_rescan_delivery(org_id=uuid.uuid4(), repo_id=uuid.uuid4())

    call = _FakeWebhookLogRepo.last_call
    payload = call["payload"]
    assert payload["pr_number"] == 0
    assert payload["base_sha"] == "BASE_SHA_FROM_TRACKED"
    assert payload["head_sha"] == "REMOTE_HEAD_SHA"
    assert payload["full_name"] == "owner/fakerepo"
    assert payload["trigger"] == "operator_button"
    assert call["event_type"] == mod.EVENT_TYPE_REPO_SCAN


async def test_explicit_trigger_propagates_to_payload(
    _patched: dict[str, Any],
) -> None:
    """A scheduled or API-driven rescan should be distinguishable in logs."""
    await mod.enqueue_rescan_delivery(org_id=uuid.uuid4(), repo_id=uuid.uuid4(), trigger="api")

    assert _FakeWebhookLogRepo.last_call["payload"]["trigger"] == "api"


async def test_raises_when_repo_missing(_patched: dict[str, Any]) -> None:
    """Unknown ``repo_id`` for the org → 404-mapped exception."""
    _FakeTrackedRepoRepo.repo = None

    with pytest.raises(mod.RescanRepoNotFoundError):
        await mod.enqueue_rescan_delivery(org_id=uuid.uuid4(), repo_id=uuid.uuid4())

    assert _patched["publish_calls"] == []  # no XADD on failure


async def test_raises_when_repo_path_is_null(_patched: dict[str, Any]) -> None:
    """A repo without a local clone path can't resolve a remote head SHA."""
    repo = _FakeRepoRow()
    repo.path = ""
    _FakeTrackedRepoRepo.repo = repo

    with pytest.raises(mod.RescanRepoNotFoundError):
        await mod.enqueue_rescan_delivery(org_id=uuid.uuid4(), repo_id=uuid.uuid4())


async def test_raises_when_ls_remote_fails(_patched: dict[str, Any]) -> None:
    """Non-zero ``git ls-remote`` exit → RescanHeadResolutionError, no XADD."""
    _patched["ls_remote_result"] = ("", "fatal: ENOTFOUND", 128)

    with pytest.raises(mod.RescanHeadResolutionError, match="ls-remote"):
        await mod.enqueue_rescan_delivery(org_id=uuid.uuid4(), repo_id=uuid.uuid4())

    assert _patched["publish_calls"] == []


async def test_raises_when_ls_remote_returns_empty_sha(
    _patched: dict[str, Any],
) -> None:
    """Empty stdout from ls-remote also fails — branch may not exist on remote."""
    _patched["ls_remote_result"] = ("", "", 0)

    with pytest.raises(mod.RescanHeadResolutionError):
        await mod.enqueue_rescan_delivery(org_id=uuid.uuid4(), repo_id=uuid.uuid4())


async def test_base_sha_empty_when_tracked_head_sha_null(
    _patched: dict[str, Any],
) -> None:
    """A repo with ``last_scanned_at`` set but no ``head_sha`` shouldn't crash.

    The dispatcher's cache-miss branch will then fall through to a full
    scan — that's the correct degradation, surfaced explicitly.
    """
    repo = _FakeRepoRow()
    repo.head_sha = None  # type: ignore[assignment]
    _FakeTrackedRepoRepo.repo = repo

    await mod.enqueue_rescan_delivery(org_id=uuid.uuid4(), repo_id=uuid.uuid4())

    assert _FakeWebhookLogRepo.last_call["payload"]["base_sha"] == ""
    assert _FakeWebhookLogRepo.last_call["payload"]["head_sha"] == "REMOTE_HEAD_SHA"
