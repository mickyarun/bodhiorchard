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

"""The guard refuses the outside world; signing and git fixtures match the app."""

from __future__ import annotations

import asyncio
import socket
from pathlib import Path

import httpx
import pytest

from app.api.v1.github_webhook import _verify_github_signature
from app.services.git_operations import _detect_main_branch
from app.services.slack_verify import verify_slack_signature
from tests.fakes.git_repo import LocalGitRepo, build_git_repo, git
from tests.fakes.guard import ExternalCallBlockedError, ExternalCallGuard
from tests.fakes.http_router import FakeHttpRouter
from tests.fakes.signing import (
    signed_github_webhook,
    signed_slack_event,
    signed_slack_interaction,
)


def test_guard_refuses_dns_for_a_public_host(external_guard: ExternalCallGuard) -> None:
    with pytest.raises(ExternalCallBlockedError):
        socket.getaddrinfo("api.github.com", 443)
    assert external_guard.violations == ["network lookup for 'api.github.com'"]
    external_guard.violations.clear()


def test_guard_refuses_the_dev_database_port() -> None:
    guard = ExternalCallGuard()
    guard.blocked_ports = {5432}

    with pytest.raises(ExternalCallBlockedError):
        guard.check_address(socket.AF_INET, ("127.0.0.1", 5432))
    guard.check_address(socket.AF_INET, ("127.0.0.1", 55001))
    guard.allow_port(5432)
    guard.check_address(socket.AF_INET, ("127.0.0.1", 5432))
    assert len(guard.violations) == 1


async def test_guard_refuses_a_real_claude_spawn(external_guard: ExternalCallGuard) -> None:
    spawn = asyncio.create_subprocess_exec
    with pytest.raises(ExternalCallBlockedError):
        await spawn("/usr/local/bin/claude", "-p", "hi")
    assert external_guard.violations == ["spawn of the real 'claude' binary"]
    external_guard.violations.clear()


async def test_unmounted_http_host_fails_and_is_recorded(
    http_router: FakeHttpRouter, external_guard: ExternalCallGuard
) -> None:
    async with httpx.AsyncClient() as client:
        with pytest.raises(httpx.ConnectError):
            await client.get("https://example.org/x")
    assert external_guard.violations == ["HTTP GET https://example.org/x"]
    external_guard.violations.clear()


async def test_clients_with_their_own_transport_are_left_alone(
    http_router: FakeHttpRouter,
) -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(204))
    async with httpx.AsyncClient(transport=transport) as client:
        assert (await client.get("https://example.org/x")).status_code == 204
    assert http_router.requests == []


def test_github_signature_matches_the_webhook_verifier() -> None:
    body, headers = signed_github_webhook("s3cret", "ping", {"zen": "hi"}, "d-1")

    assert _verify_github_signature("s3cret", body, headers["X-Hub-Signature-256"])
    assert not _verify_github_signature("other", body, headers["X-Hub-Signature-256"])
    assert headers["X-GitHub-Delivery"] == "d-1"


def test_slack_event_and_interaction_signatures_match_the_verifier() -> None:
    signed = [
        signed_slack_event("s3cret", "T1", {"type": "message"}),
        signed_slack_interaction("s3cret", {"type": "block_actions"}),
    ]
    for body, headers in signed:
        ts, sig = headers["X-Slack-Request-Timestamp"], headers["X-Slack-Signature"]
        assert verify_slack_signature("s3cret", ts, body, sig) == (True, "")
        assert verify_slack_signature("wrong", ts, body, sig)[0] is False


def test_stale_slack_timestamp_is_rejected() -> None:
    body, headers = signed_slack_event("s3cret", "T1", {}, timestamp=1_000_000)

    valid, reason = verify_slack_signature(
        "s3cret", headers["X-Slack-Request-Timestamp"], body, headers["X-Slack-Signature"]
    )
    assert valid is False
    assert reason.startswith("timestamp_drift")


async def test_git_repo_has_origin_branches_and_is_reproducible(
    git_repo: LocalGitRepo, tmp_path: Path
) -> None:
    twin = build_git_repo(tmp_path / "twin", git_repo.name)

    assert git_repo.head("main") == git_repo.head("develop")
    assert git_repo.head("main") == twin.head("main")
    assert (Path(git_repo.path) / "shop/orders/service.py").is_file()
    assert await _detect_main_branch(git_repo.path) == "main"
    assert len(git(git_repo.work, "log", "--format=%H", "origin/main").split()) == 2


def test_new_commits_are_pushed_to_origin(git_repo: LocalGitRepo) -> None:
    before = git_repo.head("main")

    sha = git_repo.commit({"shop/orders/notes.py": "X = 1\n"}, "Add notes")

    assert git_repo.head("main") == sha != before
    assert git_repo.head("develop") == before
