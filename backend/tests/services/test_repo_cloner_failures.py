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

"""What the cloner leaves behind and says when git fails, and its purges.

git is replaced by a scripted stand-in here: the failures under test
(an expired token, a half-written clone) are awkward to produce with a
real git and no network.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from app.config import settings as app_settings
from app.services import repo_cloner

URL = "https://github.com/acme/widgets"
SLUG = "acme-org"
PAT = "ghp_SuperSecretToken123"


@pytest.fixture
def repos_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setattr(app_settings.storage, "data_dir", str(tmp_path / "data"))
    return app_settings.storage.repos_dir


def _script(
    monkeypatch: pytest.MonkeyPatch, *, rc: int, stderr: str, make_git_dir: bool = False
) -> list[list[str]]:
    """Every git call fails with ``stderr``; optionally after creating ``dest/.git``."""
    calls: list[list[str]] = []

    async def _fake(args: list[str], **_: Any) -> tuple[int, str, str]:
        calls.append(list(args))
        if make_git_dir and args[0] == "clone":
            (Path(args[-1]) / ".git").mkdir(parents=True)
        return rc, "", stderr

    monkeypatch.setattr(repo_cloner, "_run_git", _fake)
    return calls


class TestTokenNeverEchoed:
    """A PAT goes to git in the URL; it must not come back in the error."""

    async def test_clone_error_is_scrubbed(
        self, repos_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        stderr = (
            f"fatal: unable to access 'https://x-access-token:{PAT}@github.com/acme/widgets/': "
            f"The requested URL returned error: 403 ({PAT})"
        )
        calls = _script(monkeypatch, rc=128, stderr=stderr)

        result = await repo_cloner.clone_or_update(URL, org_slug=SLUG, pat=PAT)

        assert result.success is False
        assert PAT not in (result.error or "")
        assert "https://***:***@github.com" in (result.error or "")
        # The token did reach git, URL-quoted, under the x-access-token user.
        assert f"https://x-access-token:{PAT}@github.com/acme/widgets" in calls[0]

    async def test_url_encoded_token_variant_is_scrubbed(self) -> None:
        """git can echo the quoted form, which a literal replace would miss."""
        pat = "tok/with+chars"
        noisy = "fatal: https://x-access-token:tok%2Fwith%2Bchars@github.com/a/b failed"
        assert "tok%2F" not in repo_cloner._sanitize(noisy, pat)

    async def test_errors_are_capped(self) -> None:
        assert len(repo_cloner._sanitize("x" * 5000, None)) == 400

    async def test_fetch_failure_on_an_existing_clone_is_a_failure(
        self, repos_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A stale tree is never handed back as success."""
        (repos_dir / SLUG / "widgets" / ".git").mkdir(parents=True)
        _script(monkeypatch, rc=1, stderr=f"fatal: auth failed for {PAT}")

        result = await repo_cloner.clone_or_update(URL, org_slug=SLUG, pat=PAT)

        assert result.success is False
        assert result.error == "fatal: auth failed for ****"
        assert (repos_dir / SLUG / "widgets" / ".git").is_dir()


class TestFailedCloneCleanup:
    """A failed clone removes what it wrote, and only that."""

    async def test_removes_a_half_written_clone(
        self, repos_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _script(monkeypatch, rc=128, stderr="fatal: early EOF", make_git_dir=True)
        result = await repo_cloner.clone_or_update(URL, org_slug=SLUG)
        assert result.success is False
        assert not (repos_dir / SLUG / "widgets").exists()

    async def test_leaves_a_folder_it_did_not_create(
        self, repos_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        keep = repos_dir / SLUG / "widgets" / "notes.txt"
        keep.parent.mkdir(parents=True)
        keep.write_text("mine")
        _script(monkeypatch, rc=128, stderr="fatal: destination path already exists")

        result = await repo_cloner.clone_or_update(URL, org_slug=SLUG)

        assert result.success is False
        assert keep.read_text() == "mine"


class TestPurges:
    """Purges stay inside the org (and the repos) they were asked about."""

    def _tree(self, repos_dir: Path) -> None:
        for org, repo in [(SLUG, "widgets"), (SLUG, "gadgets"), ("other-org", "widgets")]:
            (repos_dir / org / repo / ".git").mkdir(parents=True)

    def test_purge_org_clones_only_touches_that_org(self, repos_dir: Path) -> None:
        self._tree(repos_dir)
        assert repo_cloner.purge_org_clones(SLUG) == 2
        assert not (repos_dir / SLUG).exists()
        assert (repos_dir / "other-org" / "widgets").is_dir()

    def test_purge_org_clones_of_an_unknown_org_is_a_no_op(self, repos_dir: Path) -> None:
        assert repo_cloner.purge_org_clones("nobody") == 0

    def test_purge_repo_clones_only_touches_named_repos(self, repos_dir: Path) -> None:
        self._tree(repos_dir)
        assert repo_cloner.purge_repo_clones(SLUG, ["widgets", "missing"]) == 1
        assert (repos_dir / SLUG / "gadgets").is_dir()
        assert (repos_dir / "other-org" / "widgets").is_dir()

    @pytest.mark.parametrize("bad", ["../other-org", "a/b", "", "x y"])
    def test_unsafe_names_raise_and_delete_nothing(self, repos_dir: Path, bad: str) -> None:
        self._tree(repos_dir)
        with pytest.raises(ValueError):
            repo_cloner.purge_repo_clones(SLUG, [bad])
        with pytest.raises(ValueError):
            repo_cloner.purge_org_clones(bad)
        assert sum(1 for _ in repos_dir.glob("*/*/.git")) == 3
