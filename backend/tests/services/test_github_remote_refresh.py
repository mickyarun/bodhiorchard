# Copyright 2025-2026 Arun Rajkumar
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
"""Unit tests for ``github_remote_refresh.refresh_origin_token``.

Pins the best-effort contract: every short-circuit branch returns
``False`` without raising, and the happy path composes the App-style
URL with ``x-access-token`` and the freshly-minted token.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import github_remote_refresh


@pytest.fixture
def org_id() -> uuid.UUID:
    return uuid.uuid4()


def _mock_db_with_repo(repo: object | None) -> MagicMock:
    db = MagicMock()
    db.get = AsyncMock()
    # ``TrackedRepoRepository.get_by_path`` is what the helper calls;
    # patched at the module level in each test.
    db._repo_to_return = repo  # type: ignore[attr-defined]
    return db


def _patch_get_by_path(db: MagicMock):  # type: ignore[no-untyped-def]
    """Patch ``TrackedRepoRepository.get_by_path`` to return ``db._repo_to_return``."""
    return patch(
        "app.services.github_remote_refresh.TrackedRepoRepository.get_by_path",
        new=AsyncMock(return_value=db._repo_to_return),
    )


async def test_returns_false_when_repo_not_tracked(org_id: uuid.UUID) -> None:
    db = _mock_db_with_repo(None)
    with _patch_get_by_path(db):
        result = await github_remote_refresh.refresh_origin_token(
            working_dir="/some/path",
            org_id=org_id,
            db=db,
        )
    assert result is False
    db.get.assert_not_called()


async def test_returns_false_when_repo_has_no_github_link(org_id: uuid.UUID) -> None:
    repo = MagicMock()
    repo.github_repo_full_name = None
    db = _mock_db_with_repo(repo)
    with _patch_get_by_path(db):
        result = await github_remote_refresh.refresh_origin_token(
            working_dir="/some/path",
            org_id=org_id,
            db=db,
        )
    assert result is False


async def test_returns_false_when_no_installation_token(org_id: uuid.UUID) -> None:
    repo = MagicMock()
    repo.github_repo_full_name = "octocat/hello"
    db = _mock_db_with_repo(repo)
    db.get.return_value = MagicMock()
    with (
        _patch_get_by_path(db),
        patch.object(
            github_remote_refresh, "get_installation_token", new=AsyncMock(return_value=None)
        ),
    ):
        result = await github_remote_refresh.refresh_origin_token(
            working_dir="/some/path",
            org_id=org_id,
            db=db,
        )
    assert result is False


async def test_happy_path_composes_x_access_token_url(org_id: uuid.UUID) -> None:
    repo = MagicMock()
    repo.github_repo_full_name = "octocat/hello"
    db = _mock_db_with_repo(repo)
    db.get.return_value = MagicMock()

    captured: dict[str, object] = {}

    async def fake_run_git(args: list[str], cwd: str) -> tuple[str, str, int]:
        captured["args"] = args
        captured["cwd"] = cwd
        return ("", "", 0)

    with (
        _patch_get_by_path(db),
        patch.object(
            github_remote_refresh,
            "get_installation_token",
            new=AsyncMock(return_value="ghs_FRESH_TOKEN"),
        ),
        patch.object(github_remote_refresh, "run_git", new=fake_run_git),
    ):
        result = await github_remote_refresh.refresh_origin_token(
            working_dir="/clone/octocat-hello",
            org_id=org_id,
            db=db,
        )

    assert result is True
    assert captured["cwd"] == "/clone/octocat-hello"
    args = captured["args"]
    assert isinstance(args, list)
    assert args[:3] == ["remote", "set-url", "origin"]
    assert "x-access-token:ghs_FRESH_TOKEN@github.com/octocat/hello.git" in args[3]


async def test_token_redacted_from_failure_log(org_id: uuid.UUID) -> None:
    repo = MagicMock()
    repo.github_repo_full_name = "octocat/hello"
    db = _mock_db_with_repo(repo)
    db.get.return_value = MagicMock()

    async def failing_run_git(args: list[str], cwd: str) -> tuple[str, str, int]:
        # Simulate git echoing the URL back in its error message.
        return ("", "fatal: bad URL https://x-access-token:ghs_SECRET@github.com/...", 1)

    log_calls: list[dict[str, object]] = []
    with (
        _patch_get_by_path(db),
        patch.object(
            github_remote_refresh,
            "get_installation_token",
            new=AsyncMock(return_value="ghs_SECRET"),
        ),
        patch.object(github_remote_refresh, "run_git", new=failing_run_git),
        patch.object(
            github_remote_refresh.logger,
            "warning",
            side_effect=lambda *a, **kw: log_calls.append(kw),
        ),
    ):
        result = await github_remote_refresh.refresh_origin_token(
            working_dir="/clone/x",
            org_id=org_id,
            db=db,
        )

    assert result is False
    assert log_calls, "expected origin_refresh_failed warning"
    logged_stderr = str(log_calls[0].get("stderr", ""))
    assert "ghs_SECRET" not in logged_stderr
    assert "<redacted>" in logged_stderr
