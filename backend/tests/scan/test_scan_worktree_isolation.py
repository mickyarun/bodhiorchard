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

"""One org's scan never reuses another org's worktree.

Scan worktrees used to be keyed by the repo's folder name, so org B's
``widgets`` landed in org A's ``widgets`` worktree, found it healthy and
indexed A's code. Worktrees are now keyed by org and repo id, and a
folder that isn't a worktree of the repo being scanned is rebuilt rather
than reused. These tests drive real git repos.
"""

from __future__ import annotations

import subprocess
import uuid
from pathlib import Path

import pytest

from app.config import settings as app_settings
from app.services.scan.stages.ingest_worktree import ensure_scan_test_worktree

_GIT_IDENTITY = ("-c", "user.name=Test", "-c", "user.email=test@example.com")


def _git(cwd: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", *_GIT_IDENTITY, "-C", str(cwd), *args], check=True, capture_output=True, text=True
    )
    return done.stdout.strip()


def _make_repo(path: Path, marker: str) -> Path:
    """A repo with one commit on ``main`` whose checkout is a feature branch."""
    path.mkdir(parents=True)
    _git(path, "init", "-q", "-b", "main")
    (path / "owner.txt").write_text(marker)
    _git(path, "add", "owner.txt")
    _git(path, "commit", "-q", "-m", "init")
    _git(path, "checkout", "-q", "-b", "feature")
    return path


@pytest.fixture(autouse=True)
def data_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setattr(app_settings.storage, "data_dir", str(tmp_path / "data"))
    return tmp_path / "data"


@pytest.fixture
def two_orgs(tmp_path: Path) -> tuple[Path, Path]:
    """Same-named repos in two orgs, each holding its own org's code."""
    return (
        _make_repo(tmp_path / "repos" / "org-a" / "widgets", "org A\n"),
        _make_repo(tmp_path / "repos" / "org-b" / "widgets", "org B\n"),
    )


async def test_same_named_repos_in_two_orgs_get_their_own_worktrees(
    two_orgs: tuple[Path, Path],
) -> None:
    repo_a, repo_b = two_orgs
    wt_a = await ensure_scan_test_worktree(
        str(repo_a), "main", skip_fetch=True, org_id=uuid.uuid4(), repo_id=uuid.uuid4()
    )
    wt_b = await ensure_scan_test_worktree(
        str(repo_b), "main", skip_fetch=True, org_id=uuid.uuid4(), repo_id=uuid.uuid4()
    )

    assert wt_a != wt_b
    assert Path(wt_a, "owner.txt").read_text() == "org A\n"
    assert Path(wt_b, "owner.txt").read_text() == "org B\n"


async def test_sandbox_runs_without_ids_are_kept_apart_too(two_orgs: tuple[Path, Path]) -> None:
    repo_a, repo_b = two_orgs
    wt_a = await ensure_scan_test_worktree(str(repo_a), "main", skip_fetch=True)
    wt_b = await ensure_scan_test_worktree(str(repo_b), "main", skip_fetch=True)

    assert wt_a != wt_b
    assert Path(wt_b, "owner.txt").read_text() == "org B\n"


async def test_a_foreign_worktree_in_the_folder_is_rebuilt_not_reused(
    two_orgs: tuple[Path, Path],
) -> None:
    repo_a, repo_b = two_orgs
    org_b, repo_b_id = uuid.uuid4(), uuid.uuid4()
    first = await ensure_scan_test_worktree(
        str(repo_b), "main", skip_fetch=True, org_id=org_b, repo_id=repo_b_id
    )
    # Something left a worktree of org A's repo where org B's belongs.
    _git(repo_b, "worktree", "remove", "--force", first)
    _git(repo_a, "worktree", "add", "-q", first, "main")
    assert Path(first, "owner.txt").read_text() == "org A\n"

    again = await ensure_scan_test_worktree(
        str(repo_b), "main", skip_fetch=True, org_id=org_b, repo_id=repo_b_id
    )

    assert again == first
    assert Path(again, "owner.txt").read_text() == "org B\n"


async def test_its_own_healthy_worktree_is_reused(two_orgs: tuple[Path, Path]) -> None:
    _, repo_b = two_orgs
    ids = {"org_id": uuid.uuid4(), "repo_id": uuid.uuid4()}
    first = await ensure_scan_test_worktree(str(repo_b), "main", skip_fetch=True, **ids)
    Path(first, "untracked.txt").write_text("kept\n")

    again = await ensure_scan_test_worktree(str(repo_b), "main", skip_fetch=True, **ids)

    assert again == first
    assert Path(again, "untracked.txt").read_text() == "kept\n"


async def test_a_plain_folder_inside_the_repo_itself_is_rebuilt_not_reset(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A data dir inside the tracked checkout must never reset the user's branch."""
    repo = _make_repo(tmp_path / "checkout", "mine\n")
    (repo / "wip.txt").write_text("feature work\n")
    _git(repo, "add", "wip.txt")
    _git(repo, "commit", "-q", "-m", "feature work")
    feature_head = _git(repo, "rev-parse", "HEAD")
    monkeypatch.setattr(app_settings.storage, "data_dir", str(repo / "data"))
    ids = {"org_id": uuid.uuid4(), "repo_id": uuid.uuid4()}
    first = await ensure_scan_test_worktree(str(repo), "main", skip_fetch=True, **ids)
    # Leave a plain folder (no ``.git`` link) where the worktree was.
    _git(repo, "worktree", "remove", "--force", first)
    Path(first).mkdir(parents=True)

    again = await ensure_scan_test_worktree(str(repo), "main", skip_fetch=False, **ids)

    assert _git(repo, "rev-parse", "HEAD") == feature_head
    assert _git(repo, "rev-parse", "--abbrev-ref", "HEAD") == "feature"
    assert Path(again, ".git").is_file()
    assert not Path(again, "wip.txt").exists()


async def test_its_own_worktree_is_reused_through_a_symlinked_data_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, two_orgs: tuple[Path, Path]
) -> None:
    """Git records resolved paths; a symlinked data dir must still match ours."""
    _, repo_b = two_orgs
    (tmp_path / "real").mkdir()
    (tmp_path / "link").symlink_to(tmp_path / "real", target_is_directory=True)
    monkeypatch.setattr(app_settings.storage, "data_dir", str(tmp_path / "link" / "data"))
    ids = {"org_id": uuid.uuid4(), "repo_id": uuid.uuid4()}
    first = await ensure_scan_test_worktree(str(repo_b), "main", skip_fetch=True, **ids)
    Path(first, "untracked.txt").write_text("kept\n")

    again = await ensure_scan_test_worktree(str(repo_b), "main", skip_fetch=True, **ids)

    assert again == first
    assert Path(again, "untracked.txt").read_text() == "kept\n"
