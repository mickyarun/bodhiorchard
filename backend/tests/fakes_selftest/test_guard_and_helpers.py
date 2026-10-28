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

"""The guard's other doors, and the small helpers next to the fakes."""

from __future__ import annotations

import os
import socket
import subprocess
from pathlib import Path

import pytest

from app.config import settings
from app.services import event_bus
from app.services.embedding_service import embedding_service
from tests.fakes.app_state import EventRecorder
from tests.fakes.embeddings import DIMENSIONS, FakeEmbedder
from tests.fakes.git_repo import LocalGitRepo, git
from tests.fakes.guard import (
    OLLAMA_PORT,
    ExternalCallBlockedError,
    ExternalCallGuard,
    is_loopback,
    settings_port,
)


def test_assert_clean_fails_the_test_once_anything_was_refused() -> None:
    guard = ExternalCallGuard()
    with pytest.raises(ExternalCallBlockedError):
        guard.check_address(socket.AF_INET, ("93.184.216.34", 443))

    with pytest.raises(pytest.fail.Exception, match="93.184.216.34:443"):
        guard.assert_clean()


def test_local_service_ports_come_from_the_settings() -> None:
    guard = ExternalCallGuard()

    assert settings_port("postgresql+asyncpg://u:p@localhost:6543/db") == 6543
    assert settings_port("redis://127.0.0.1") == 6379
    assert settings_port("https://api.example.test") is None
    assert OLLAMA_PORT in guard.blocked_ports
    db_port = settings_port(settings.db.database_url)
    assert db_port is None or db_port in guard.blocked_ports
    with pytest.raises(ExternalCallBlockedError):
        guard.check_address(socket.AF_INET, ("127.0.0.1", OLLAMA_PORT))
    guard.allow_port(OLLAMA_PORT)
    guard.check_address(socket.AF_INET, ("127.0.0.1", OLLAMA_PORT))


def test_loopback_detection_covers_names_and_mapped_addresses() -> None:
    assert is_loopback("localhost")
    assert is_loopback("::1")
    assert is_loopback("::ffff:127.0.0.1")
    assert not is_loopback("10.0.0.1")
    assert not is_loopback("api.github.com")


@pytest.mark.parametrize(
    "argv",
    [
        ["claude", "-p", "x"],
        ["sandbox-exec", "-p", "(profile)", "/usr/local/bin/claude", "-p", "x"],
        "env FOO=1 codex exec hi",
        [b"copilot"],
    ],
)
def test_agent_binaries_are_refused_wherever_they_appear(
    argv: str | list[str] | list[bytes], external_guard: ExternalCallGuard
) -> None:
    with pytest.raises(ExternalCallBlockedError):
        subprocess.Popen(argv, shell=isinstance(argv, str))  # noqa: S603
    external_guard.violations.clear()


def test_git_can_only_reach_local_repositories(git_repo: LocalGitRepo) -> None:
    assert os.environ["GIT_ALLOW_PROTOCOL"] == "file"
    done = subprocess.run(
        ["git", "ls-remote", "https://github.com/acme/shop.git"],
        cwd=git_repo.work,
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode != 0
    assert "not allowed" in done.stderr


def test_sandbox_and_mock_switches_are_cleared() -> None:
    assert "BODHIORCHARD_HYBRID_SANDBOX" not in os.environ
    assert "BODHI_MOCK_PR_FILES_PATH" not in os.environ


async def test_embedder_pins_phrases_and_can_fail(fake_embeddings: FakeEmbedder) -> None:
    unit = [1.0] + [0.0] * (DIMENSIONS - 1)
    fake_embeddings.pin("payments", unit)

    assert await embedding_service.embed("all about payments") == unit
    same = await embedding_service.embed("orders")
    assert same == await embedding_service.embed("orders")
    assert len(same) == DIMENSIONS
    fake_embeddings.failing = True
    with pytest.raises(RuntimeError):
        await embedding_service.embed("orders")
    assert await embedding_service.check() == (False, "fake embedding failure")


async def test_event_recorder_sees_every_publish(event_recorder: EventRecorder) -> None:
    event_bus.publish("scan:1", {"status": "running"})
    event_bus.publish("scan:1", {"status": "done"})

    await event_recorder.settle()

    assert event_recorder.payloads("scan:1") == [{"status": "running"}, {"status": "done"}]


def test_data_dir_redirects_the_settings(data_dir: Path) -> None:
    assert settings.storage.data_dir == str(data_dir)
    assert data_dir.is_dir()


def test_fixture_commits_survive_the_app_rewriting_origin(git_repo: LocalGitRepo) -> None:
    git(git_repo.work, "remote", "set-url", "origin", "https://github.com/acme/shop.git")

    sha = git_repo.commit({"shop/notes.py": "NOTE = 1\n"}, "Notes")

    assert git_repo.head("main") == sha
    with pytest.raises(RuntimeError, match="not allowed"):
        git(git_repo.work, "fetch", "origin")
