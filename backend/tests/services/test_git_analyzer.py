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

"""Behavioural tests for the per-commit line-churn scoring."""

import os
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.services.git_analyzer import analyze_repo_skills


def _run(repo: Path, *args: str, env: dict[str, str] | None = None) -> None:
    """Run a git command, raising on non-zero exit."""
    subprocess.run(["git", "-C", str(repo), *args], check=True, env=env, capture_output=True)


def _commit(
    repo: Path,
    author_name: str,
    author_email: str,
    when: datetime,
    files: dict[str, str],
    message: str,
) -> None:
    """Write files, stage, and commit with author + date pinned.

    Merges author overrides into the parent environment rather than
    replacing it — macOS git resolves user info via libsecret/keychain
    and needs the inherited PATH/HOME to function.
    """
    for rel_path, contents in files.items():
        target = repo / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(contents)
    _run(repo, "add", "-A")
    iso = when.isoformat()
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": author_name,
        "GIT_AUTHOR_EMAIL": author_email,
        "GIT_COMMITTER_NAME": author_name,
        "GIT_COMMITTER_EMAIL": author_email,
        "GIT_AUTHOR_DATE": iso,
        "GIT_COMMITTER_DATE": iso,
    }
    _run(repo, "commit", "-m", message, env=env)


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """Build a throwaway repo for analyzer tests."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _run(repo, "init", "-q", "-b", "main")
    _run(repo, "config", "user.email", "setup@local")
    _run(repo, "config", "user.name", "Setup")
    _run(repo, "config", "commit.gpgsign", "false")
    return repo


@pytest.mark.asyncio
async def test_big_old_commit_beats_many_tiny_recent_ones(git_repo: Path) -> None:
    """The 2FA bug shape — author A wrote 500 lines once long ago,
    author B made 5 tiny recent fixes. A must rank above B."""
    now = datetime.now(UTC)
    # Author A: one substantial commit 120 days ago
    _commit(
        git_repo,
        "Author A",
        "a@example.com",
        now - timedelta(days=120),
        {"src/auth/login.py": "\n".join(f"line {i}" for i in range(500)) + "\n"},
        "feat: initial login",
    )
    # Author B: five 3-line tweaks today
    for i in range(5):
        _commit(
            git_repo,
            "Author B",
            "b@example.com",
            now - timedelta(minutes=i),
            {"src/auth/login.py": "\n".join(f"line {j}" for j in range(500 + i + 1)) + "\n"},
            f"fix: tweak {i}",
        )

    entries = await analyze_repo_skills(str(git_repo))
    by_email = {(e.email, e.module): e for e in entries}
    a = by_email[("a@example.com", "src")]
    b = by_email[("b@example.com", "src")]

    assert a.lines_added >= 500, f"expected ~500 lines from A, got {a.lines_added}"
    assert b.lines_added == 5, f"expected 5 lines from B, got {b.lines_added}"
    assert a.skill_score > b.skill_score, f"A ({a.skill_score}) should outrank B ({b.skill_score})"


@pytest.mark.asyncio
async def test_noise_files_excluded(git_repo: Path) -> None:
    """Lock files and minified bundles must not inflate scores."""
    now = datetime.now(UTC)
    _commit(
        git_repo,
        "Noisy Dev",
        "noise@example.com",
        now,
        {
            "package-lock.json": "\n".join(f"x{i}" for i in range(2000)) + "\n",
            "dist/app.min.js": "\n".join(f"y{i}" for i in range(2000)) + "\n",
            "src/real.py": "real_code = 1\n",
        },
        "chore: noisy commit",
    )

    entries = await analyze_repo_skills(str(git_repo))
    noisy = next(e for e in entries if e.email == "noise@example.com")
    # Only the 1 line in src/real.py should count.
    assert noisy.lines_added == 1, f"noise filter failed: {noisy.lines_added} lines counted"


@pytest.mark.asyncio
async def test_branch_param_walks_named_branch(git_repo: Path) -> None:
    """Commits made only on a side branch must be picked up when
    that branch is passed in, and ignored when walking main."""
    now = datetime.now(UTC)
    # Baseline commit on main
    _commit(
        git_repo,
        "Trunk",
        "trunk@example.com",
        now - timedelta(days=10),
        {"src/seed.py": "x = 1\n"},
        "init",
    )
    # Create develop with a feature commit not on main
    _run(git_repo, "checkout", "-q", "-b", "develop")
    _commit(
        git_repo,
        "Branched",
        "branched@example.com",
        now - timedelta(days=5),
        {"src/feature.py": "\n".join(f"l{i}" for i in range(40)) + "\n"},
        "feat: branched work",
    )
    _run(git_repo, "checkout", "-q", "main")

    on_main = await analyze_repo_skills(str(git_repo))
    on_dev = await analyze_repo_skills(str(git_repo), branch="develop")

    main_emails = {e.email for e in on_main}
    dev_emails = {e.email for e in on_dev}
    assert "branched@example.com" not in main_emails
    assert "branched@example.com" in dev_emails


@pytest.mark.asyncio
async def test_rename_credited_to_new_path(git_repo: Path) -> None:
    """Renames must attribute lines to the new path, not the rename author.

    Guards against the three rename shapes emitted by ``git diff-tree
    --numstat -M`` collapsing into a malformed path (``new}/file``)
    and silently dropping the file from the language filter.
    """
    now = datetime.now(UTC)
    _commit(
        git_repo,
        "Original",
        "orig@example.com",
        now - timedelta(days=30),
        {"src/old_module/login.py": "\n".join(f"line {i}" for i in range(60)) + "\n"},
        "feat: initial",
    )
    # Rename the directory; pure rename should record ~0 line changes
    # and the new path must be the credited location.
    new_path = git_repo / "src" / "new_module"
    (git_repo / "src" / "old_module").rename(new_path)
    _run(git_repo, "add", "-A")
    iso = (now - timedelta(days=5)).isoformat()
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Renamer",
        "GIT_AUTHOR_EMAIL": "renamer@example.com",
        "GIT_COMMITTER_NAME": "Renamer",
        "GIT_COMMITTER_EMAIL": "renamer@example.com",
        "GIT_AUTHOR_DATE": iso,
        "GIT_COMMITTER_DATE": iso,
    }
    _run(git_repo, "commit", "-m", "refactor: rename module", env=env)

    entries = await analyze_repo_skills(str(git_repo))
    by_email = {e.email: e for e in entries}
    # Renamer should not get credit for the 60 lines.
    assert by_email["renamer@example.com"].lines_added == 0
    # Original author keeps the 60 lines they actually wrote.
    assert by_email["orig@example.com"].lines_added == 60
