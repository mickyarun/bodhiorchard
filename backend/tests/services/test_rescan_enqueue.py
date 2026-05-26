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


class _FakeOrganizationRepo:
    """Returns a sentinel "org" object — the helper only forwards it to
    ``refresh_origin_auth``, which the tests stub out, so the value never
    needs real ``Organization`` fields.
    """

    org: Any = object()

    def __init__(self, *_a: Any, **_kw: Any) -> None:
        pass

    async def get_by_id(self, _org_id: uuid.UUID) -> Any:
        return self.org


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
        "ls_remote_result": ("abcdef0123456789abcdef0123456789abcdef01\trefs/heads/main\n", "", 0),
    }

    @asynccontextmanager
    async def _fake_session(_org_id: uuid.UUID) -> Any:
        yield _FakeDb()

    async def _fake_run_git(args: list[str], cwd: str, **kwargs: Any) -> tuple[str, str, int]:
        # ``ls-remote`` may be invoked with a leading ``-c
        # remote.origin.url=...`` override on the App-HTTPS fallback path
        # — find the first non-``-c`` token so this fake works for both
        # the primary call and the retry.
        i = 0
        while i < len(args) and args[i] == "-c":
            i += 2
        assert args[i] == "ls-remote"
        # Capture kwargs so tests can assert ``env`` propagation —
        # without this, dropping ``env=env`` on the primary call would
        # silently regress the SSH-refresh half of the fix.
        captured["ls_remote_calls"].append({"args": list(args), "kwargs": dict(kwargs)})
        return captured["ls_remote_result"]

    async def _fake_publish(*, org_id: uuid.UUID, repo_id: uuid.UUID, delivery_id: str) -> bool:
        captured["publish_calls"].append(
            {"org_id": org_id, "repo_id": repo_id, "delivery_id": delivery_id}
        )
        return True

    async def _fake_detect_main(_repo_path: str) -> str | None:
        return "main"

    async def _fake_refresh_origin_auth(_repo_path: str, _org: Any) -> dict[str, str] | None:
        captured["refresh_calls"].append({"repo_path": _repo_path, "org": _org})
        return None

    async def _fake_build_app_https_url(_repo_path: str, _org: Any) -> str | None:
        return None

    captured["ls_remote_calls"] = []
    captured["refresh_calls"] = []

    monkeypatch.setattr(mod, "with_session", _fake_session)
    monkeypatch.setattr(mod, "TrackedRepoRepository", _FakeTrackedRepoRepo)
    monkeypatch.setattr(mod, "OrganizationRepository", _FakeOrganizationRepo)
    monkeypatch.setattr(mod, "WebhookLogRepository", _FakeWebhookLogRepo)
    monkeypatch.setattr(mod, "run_git", _fake_run_git)
    monkeypatch.setattr(mod, "publish_pr_merge_delivery", _fake_publish)
    monkeypatch.setattr(mod, "_detect_main_branch", _fake_detect_main)
    monkeypatch.setattr(mod, "refresh_origin_auth", _fake_refresh_origin_auth)
    monkeypatch.setattr(mod, "build_app_https_url_for_origin", _fake_build_app_https_url)
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
    assert payload["head_sha"] == "abcdef0123456789abcdef0123456789abcdef01"
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


async def test_raises_when_ls_remote_returns_non_sha_token(
    _patched: dict[str, Any],
) -> None:
    """First token isn't a hex object id — reject before it reaches the dispatcher."""
    _patched["ls_remote_result"] = ("<!doctype html><html>...\n", "", 0)

    with pytest.raises(mod.RescanHeadResolutionError, match="non-SHA token"):
        await mod.enqueue_rescan_delivery(org_id=uuid.uuid4(), repo_id=uuid.uuid4())

    assert _patched["publish_calls"] == []


async def test_raises_when_ls_remote_returns_multiple_refs(
    _patched: dict[str, Any],
) -> None:
    """Ambiguous branch name → multiple lines. Refuse rather than pick the first."""
    _patched["ls_remote_result"] = (
        "abcdef0123456789abcdef0123456789abcdef01\trefs/heads/main\n"
        "1111111111111111111111111111111111111111\trefs/heads/main-2\n",
        "",
        0,
    )

    with pytest.raises(mod.RescanHeadResolutionError, match="2 refs"):
        await mod.enqueue_rescan_delivery(org_id=uuid.uuid4(), repo_id=uuid.uuid4())

    assert _patched["publish_calls"] == []


async def test_accepts_sha256_object_id(_patched: dict[str, Any]) -> None:
    """64-char SHA-256 object IDs (git's transitional format) are accepted too."""
    sha256 = "a" * 64
    _patched["ls_remote_result"] = (f"{sha256}\trefs/heads/main\n", "", 0)

    delivery_id = await mod.enqueue_rescan_delivery(org_id=uuid.uuid4(), repo_id=uuid.uuid4())

    assert delivery_id.startswith("rescan-")
    assert _FakeWebhookLogRepo.last_call["payload"]["head_sha"] == sha256


async def test_raises_collision_when_record_replay_row_returns_false(
    _patched: dict[str, Any],
) -> None:
    """``ON CONFLICT DO NOTHING`` returning False = pre-existing row.

    Structurally impossible with uuid4 but if it ever fires we want a
    loud failure, not a silent no-op delivery the operator watches
    forever waiting for "done".
    """
    _FakeWebhookLogRepo.inserted = False

    with pytest.raises(mod.RescanDeliveryIdCollisionError):
        await mod.enqueue_rescan_delivery(org_id=uuid.uuid4(), repo_id=uuid.uuid4())

    # And critically — no XADD landed on the stream for a delivery the
    # consumer would never find a fresh row for.
    assert _patched["publish_calls"] == []


async def test_refreshes_origin_auth_before_ls_remote(
    _patched: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``refresh_origin_auth`` must run before ls-remote, and its env
    (e.g. ``GIT_SSH_COMMAND`` for SSH origins) must propagate to git.

    Regression for the failure mode where rescan reused the clone-time
    GitHub App installation token (TTL ~1h) and GitHub returned
    "Invalid username or token. Password authentication is not supported"
    once that token expired. Also pins the SSH half of the fix: dropping
    the ``env=env`` kwarg on the primary call would silently break
    SSH-deploy-key repos.
    """
    ssh_env = {"GIT_SSH_COMMAND": "ssh -i /fake/key"}

    async def _fake_refresh(_repo_path: str, _org: Any) -> dict[str, str] | None:
        _patched["refresh_calls"].append({"repo_path": _repo_path, "org": _org})
        return ssh_env

    monkeypatch.setattr(mod, "refresh_origin_auth", _fake_refresh)

    await mod.enqueue_rescan_delivery(org_id=uuid.uuid4(), repo_id=uuid.uuid4())

    assert len(_patched["refresh_calls"]) == 1
    assert _patched["refresh_calls"][0]["repo_path"] == "/tmp/fakerepo"
    # The org loaded from ``OrganizationRepository.get_by_id`` is what
    # ``refresh_origin_auth`` receives — not ``None`` — so the helper
    # actually has the credentials it needs to mint a fresh token.
    assert _patched["refresh_calls"][0]["org"] is _FakeOrganizationRepo.org
    # The env returned by ``refresh_origin_auth`` reached ``run_git``.
    assert _patched["ls_remote_calls"][0]["kwargs"].get("env") == ssh_env


async def test_falls_back_to_app_https_override_on_ls_remote_failure(
    _patched: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SSH ls-remote fail → retry with ``-c remote.origin.url=<App-HTTPS>``.

    Mirrors the fallback in ``scan.stages.ingest_worktree._reset_to_remote``
    so SSH-cloned repos whose deploy key isn't registered still resolve
    head SHA via the org's GitHub App token.
    """
    calls: list[list[str]] = []
    ssh_failure = ("", "fatal: Could not read from remote", 128)
    https_success = (
        "abcdef0123456789abcdef0123456789abcdef01\trefs/heads/main\n",
        "",
        0,
    )

    async def _fake_run_git(args: list[str], cwd: str, **_kw: Any) -> tuple[str, str, int]:
        calls.append(list(args))
        return ssh_failure if len(calls) == 1 else https_success

    async def _fake_build_app_https_url(_repo_path: str, _org: Any) -> str | None:
        return "https://x-access-token:fresh@github.com/owner/repo.git"

    monkeypatch.setattr(mod, "run_git", _fake_run_git)
    monkeypatch.setattr(mod, "build_app_https_url_for_origin", _fake_build_app_https_url)

    await mod.enqueue_rescan_delivery(org_id=uuid.uuid4(), repo_id=uuid.uuid4())

    assert len(calls) == 2
    # First attempt: vanilla ls-remote against persistent origin.
    assert calls[0] == ["ls-remote", "origin", "main"]
    # Second attempt: one-shot ``-c remote.origin.url=...`` override so
    # the persistent SSH remote in ``.git/config`` stays untouched.
    assert calls[1][0] == "-c"
    assert calls[1][1].startswith("remote.origin.url=https://x-access-token:")
    assert calls[1][2:] == ["ls-remote", "origin", "main"]


async def test_error_message_scrubs_app_token_from_stderr(
    _patched: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A leaked App token in git stderr must not surface in the raised error.

    The App-HTTPS fallback passes the URL via ``-c remote.origin.url=...``.
    Git can echo that URL back into stderr on failure (e.g. ``fatal:
    unable to access 'https://x-access-token:ghs_xxx@github.com/...'``).
    The error message must redact the credential segment before raising,
    so live tokens never reach logs, the API response, or webhook_logs.
    """
    leaked_url = "https://x-access-token:ghs_SECRETTOKEN@github.com/owner/repo.git"
    primary_failure = (
        "",
        f"fatal: unable to access '{leaked_url}/': forbidden",
        128,
    )
    fallback_failure = ("", "fatal: still broken", 128)
    seq = iter([primary_failure, fallback_failure])

    async def _fake_run_git(args: list[str], cwd: str, **_kw: Any) -> tuple[str, str, int]:
        return next(seq)

    async def _fake_build_app_https_url(_repo_path: str, _org: Any) -> str | None:
        return leaked_url

    monkeypatch.setattr(mod, "run_git", _fake_run_git)
    monkeypatch.setattr(mod, "build_app_https_url_for_origin", _fake_build_app_https_url)

    with pytest.raises(mod.RescanHeadResolutionError) as exc_info:
        await mod.enqueue_rescan_delivery(org_id=uuid.uuid4(), repo_id=uuid.uuid4())

    msg = str(exc_info.value)
    assert "ghs_SECRETTOKEN" not in msg
    assert "x-access-token:ghs_" not in msg
    # Both legs' stderrs are preserved (after scrubbing) so operators
    # can tell which attempt failed without reading the raw git log.
    assert "primary=" in msg and "fallback=" in msg


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
    assert (
        _FakeWebhookLogRepo.last_call["payload"]["head_sha"]
        == "abcdef0123456789abcdef0123456789abcdef01"
    )
