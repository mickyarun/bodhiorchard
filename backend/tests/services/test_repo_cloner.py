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

"""``clone_or_update`` against a real git, with the network taken out.

GitHub is never contacted: the subprocess wrapper rewrites the GitHub
URL to a bare repository in ``tmp_path`` and then runs the real ``git``,
so the clone layout, default-branch detection and the update path are
the real thing. Every clone lands under a ``data_dir`` in ``tmp_path``.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any

import pytest

from app.config import settings as app_settings
from app.services import repo_cloner
from tests.api.v1.repo_path_support import run_git

URL = "https://github.com/acme/widgets"
SLUG = "acme-org"
RealGit = Callable[..., Coroutine[Any, Any, tuple[int, str, str]]]


@pytest.fixture
def repos_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setattr(app_settings.storage, "data_dir", str(tmp_path / "data"))
    return app_settings.storage.repos_dir


@pytest.fixture
def origin(tmp_path: Path) -> Path:
    """A bare repo on ``main`` with one commit, standing in for GitHub."""
    bare = tmp_path / "widgets.git"
    run_git("init", "-q", "--bare", "-b", "main", str(bare), cwd=tmp_path)
    seed = tmp_path / "seed"
    run_git("clone", "-q", str(bare), str(seed), cwd=tmp_path)
    run_git("commit", "-q", "--allow-empty", "-m", "one", cwd=seed)
    run_git("push", "-q", "origin", "HEAD:main", "HEAD:develop", cwd=seed)
    return bare


@pytest.fixture
def git_calls(monkeypatch: pytest.MonkeyPatch, origin: Path) -> list[list[str]]:
    """Record git argv, swapping any GitHub URL for the local bare repo."""
    calls: list[list[str]] = []
    real: RealGit = repo_cloner._run_git

    async def _local(args: list[str], **kwargs: Any) -> tuple[int, str, str]:
        calls.append(list(args))
        swapped = [str(origin) if a.startswith("https://") else a for a in args]
        return await real(swapped, **kwargs)

    monkeypatch.setattr(repo_cloner, "_run_git", _local)
    return calls


class TestRefusesBeforeRunningGit:
    """Anything that is not a plain GitHub repo is refused up front."""

    @pytest.mark.parametrize(
        "url",
        [
            "https://gitlab.com/acme/widgets",
            "https://github.com.evil.example/acme/widgets",
            "https://github.com@evil.example/acme/widgets",
            "https://github.com/acme",
            "git@gitlab.com:acme/widgets.git",
            "file:///etc/passwd",
            "--upload-pack=touch /tmp/x",
            "",
        ],
    )
    async def test_non_github_urls(
        self, repos_dir: Path, git_calls: list[list[str]], url: str
    ) -> None:
        result = await repo_cloner.clone_or_update(url, org_slug=SLUG)
        assert result.success is False
        assert "Only GitHub URLs" in (result.error or "")
        assert git_calls == []

    @pytest.mark.parametrize(
        ("url", "slug"),
        [
            ("https://github.com/acme/wid%20gets", SLUG),
            ("https://github.com/ac;me/widgets", SLUG),
            (URL, "../other-org"),
            (URL, "acme/../../etc"),
        ],
    )
    async def test_unsafe_names(
        self, repos_dir: Path, git_calls: list[list[str]], url: str, slug: str
    ) -> None:
        result = await repo_cloner.clone_or_update(url, org_slug=slug)
        assert result.success is False
        assert result.error == "Invalid characters in owner, repo, or org slug."
        assert git_calls == []


class TestClones:
    """The happy paths, through a real git."""

    @pytest.mark.parametrize(
        "url",
        [URL, f"{URL}.git", f"{URL}/", "git@github.com:acme/widgets.git"],
    )
    async def test_lands_under_the_org_and_reads_the_default_branch(
        self,
        repos_dir: Path,
        git_calls: list[list[str]],
        monkeypatch: pytest.MonkeyPatch,
        url: str,
    ) -> None:
        monkeypatch.setattr(repo_cloner, "ssh_env", lambda: None)
        if url.startswith("git@"):
            # SSH URLs are passed through; point this one at the bare repo too.
            real = repo_cloner._run_git

            async def _ssh(args: list[str], **kwargs: Any) -> tuple[int, str, str]:
                return await real([URL if a == url else a for a in args], **kwargs)

            monkeypatch.setattr(repo_cloner, "_run_git", _ssh)

        result = await repo_cloner.clone_or_update(url, org_slug=SLUG)

        assert result.success is True, result.error
        assert result.path == str(repos_dir / SLUG / "widgets")
        assert result.default_branch == "main"
        assert (repos_dir / SLUG / "widgets" / ".git").is_dir()

    async def test_a_second_call_fetches_and_moves_to_the_branch(
        self, repos_dir: Path, git_calls: list[list[str]], origin: Path, tmp_path: Path
    ) -> None:
        first = await repo_cloner.clone_or_update(URL, org_slug=SLUG)
        assert first.success
        seed = tmp_path / "seed"
        run_git("commit", "-q", "--allow-empty", "-m", "two", cwd=seed)
        run_git("push", "-q", "origin", "HEAD:develop", cwd=seed)
        git_calls.clear()

        again = await repo_cloner.clone_or_update(URL, org_slug=SLUG, branch="develop")

        assert again.success is True, again.error
        assert [c[2] for c in git_calls[:3]] == ["remote", "fetch", "checkout"]
        dest = Path(again.path or "")
        assert run_git("rev-parse", "--abbrev-ref", "HEAD", cwd=dest).strip() == "develop"
        assert run_git("log", "-1", "--format=%s", cwd=dest).strip() == "two"

    async def test_orgs_never_share_a_clone(
        self, repos_dir: Path, git_calls: list[list[str]]
    ) -> None:
        one = await repo_cloner.clone_or_update(URL, org_slug="org-one")
        two = await repo_cloner.clone_or_update(URL, org_slug="org-two")
        assert one.path != two.path
        assert {Path(p or "").parent.name for p in (one.path, two.path)} == {"org-one", "org-two"}
