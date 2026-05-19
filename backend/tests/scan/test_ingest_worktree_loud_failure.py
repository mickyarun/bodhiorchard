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

"""Regression test for the loud-failure refactor of ``fetch_and_reset``.

The previous behaviour was: when ``git reset --hard`` failed on a
worktree path, the function silently ``shutil.rmtree``-d the worktree
and tried to rebuild it. That masked corruption AND could wipe the
filesystem out from under a concurrent reader (scan stage / narrow-
synth consumer reading the same path). The new behaviour raises a
``RuntimeError`` on both repo and worktree targets, letting orphan
recovery re-publish on the next boot.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.services.scan.stages import ingest_worktree as mod


@pytest.fixture
def _patched(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Stub ``run_git`` so we can simulate fetch success and reset failure."""
    state: dict[str, Any] = {
        "fetch_rc": 0,
        "reset_rc": 1,
        "reset_stderr": "fatal: ambiguous argument 'origin/main'",
        "calls": [],
    }

    async def _fake_run_git(args: list[str], cwd: str, **_kw: Any) -> tuple[str, str, int]:
        state["calls"].append({"args": args, "cwd": cwd})
        if args and args[0] == "fetch":
            return ("", "", state["fetch_rc"])
        if args and args[0] == "reset":
            return ("", state["reset_stderr"], state["reset_rc"])
        return ("", "", 0)

    async def _fake_has_origin(_path: str) -> bool:
        return True

    async def _fake_refresh_auth(_path: str, _org: Any) -> dict[str, str] | None:
        return None

    async def _fake_app_url(_path: str, _org: Any) -> str | None:
        return None

    monkeypatch.setattr(mod, "run_git", _fake_run_git)
    monkeypatch.setattr(mod, "_has_origin_remote", _fake_has_origin)
    monkeypatch.setattr(mod, "refresh_origin_auth", _fake_refresh_auth)
    monkeypatch.setattr(mod, "build_app_https_url_for_origin", _fake_app_url)
    return state


async def test_worktree_reset_failure_raises_no_silent_rebuild(
    _patched: dict[str, Any],
) -> None:
    """A worktree ``git reset`` failure must surface as RuntimeError.

    Old behaviour swallowed this via ``shutil.rmtree(wt_path)`` +
    ``worktree add``. New behaviour raises so the consumer's
    webhook_logs row flips to FAILED and orphan recovery handles it.
    """
    with pytest.raises(RuntimeError, match="failed to reset worktree"):
        await mod.fetch_and_reset(
            repo_path="/tmp/fakerepo",
            main_branch="main",
            worktree="/tmp/fakerepo/scan-worktree",
        )

    # No ``worktree add`` or ``worktree prune`` was attempted post-reset.
    git_subcommands = [call["args"][0] for call in _patched["calls"]]
    assert "add" not in git_subcommands
    assert "prune" not in git_subcommands


async def test_live_repo_reset_failure_still_raises(_patched: dict[str, Any]) -> None:
    """Live-repo path was already raising — verify the refactor didn't regress it."""
    with pytest.raises(RuntimeError, match="failed to reset repo"):
        await mod.fetch_and_reset(repo_path="/tmp/fakerepo", main_branch="main")


async def test_reset_success_returns_silently(_patched: dict[str, Any]) -> None:
    """Happy path: ``rc == 0`` from reset → return without raising."""
    _patched["reset_rc"] = 0

    # Should not raise.
    await mod.fetch_and_reset(
        repo_path="/tmp/fakerepo",
        main_branch="main",
        worktree="/tmp/fakerepo/scan-worktree",
    )
