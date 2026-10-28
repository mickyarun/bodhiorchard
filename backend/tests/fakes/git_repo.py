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

"""Throwaway git repositories with a real ``origin`` and no network.

:func:`build_git_repo` creates, under ``tmp_path``:

* ``<name>-origin.git`` — a bare repo playing the part of GitHub;
* ``<name>`` — a clone whose ``origin`` is that bare repo, with ``main`` and
  ``develop`` pushed and a small multi-module Python service committed, so
  ``git fetch origin``, worktrees and the real code indexer all work.

Commits use a fixed author and fixed dates and the builder ignores the
developer's global git config, so the same tree always gets the same SHAs.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from tests.fakes.sample_code import SAMPLE_TREE

_FIXED_DATE = "2026-01-05T10:00:00+00:00"
DEFAULT_AUTHOR_EMAIL = "fixture.dev@example.test"
_GIT_ENV = {
    "GIT_AUTHOR_NAME": "Fixture Dev",
    "GIT_COMMITTER_NAME": "Fixture Dev",
    "GIT_AUTHOR_DATE": _FIXED_DATE,
    "GIT_COMMITTER_DATE": _FIXED_DATE,
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_TERMINAL_PROMPT": "0",
}


def git(cwd: Path, *args: str, author_email: str = DEFAULT_AUTHOR_EMAIL) -> str:
    """Run ``git args`` in ``cwd`` with the fixture identity; return stdout."""
    identity = {"GIT_AUTHOR_EMAIL": author_email, "GIT_COMMITTER_EMAIL": author_email}
    # Drop inherited GIT_* (a git hook running pytest sets GIT_DIR and
    # GIT_INDEX_FILE, which would point these commands at the real repo).
    inherited = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env = {**inherited, **_GIT_ENV, **identity}
    done = subprocess.run(
        ["git", "-c", "commit.gpgsign=false", "-c", "init.defaultBranch=main", *args],
        cwd=cwd,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    return done.stdout.strip()


@dataclass(frozen=True)
class LocalGitRepo:
    """A working clone plus its bare ``origin``."""

    name: str
    work: Path
    origin: Path
    author_email: str = DEFAULT_AUTHOR_EMAIL

    @property
    def path(self) -> str:
        """The clone's path as the app stores it on ``tracked_repositories``."""
        return str(self.work)

    def head(self, branch: str = "main") -> str:
        """Commit SHA of ``origin/<branch>``."""
        return git(self.work, "rev-parse", f"origin/{branch}")

    def commit(self, files: dict[str, str], message: str, branch: str = "main") -> str:
        """Write ``files`` on ``branch``, commit, push to origin; return the SHA."""
        if git(self.work, "symbolic-ref", "--short", "HEAD") != branch:
            git(self.work, "checkout", "-q", branch)
        for rel, text in files.items():
            target = self.work / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text)
        git(self.work, "add", "-A")
        git(self.work, "commit", "-q", "-m", message, author_email=self.author_email)
        git(self.work, "push", "-q", "origin", branch)
        return git(self.work, "rev-parse", "HEAD")


def build_git_repo(
    root: Path,
    name: str = "shop-api",
    files: dict[str, str] | None = None,
    author_email: str = DEFAULT_AUTHOR_EMAIL,
) -> LocalGitRepo:
    """Create the bare origin and clone with ``main`` and ``develop``.

    Every commit is authored by ``author_email``. The scan's skill extraction
    turns git authors into org members, and an email is unique across orgs,
    so tests that scan in several orgs pass a distinct author per repo.
    """
    origin = root / f"{name}-origin.git"
    work = root / name
    origin.mkdir(parents=True)
    git(origin, "init", "-q", "--bare")
    work.mkdir()
    git(work, "init", "-q")
    git(work, "remote", "add", "origin", str(origin))
    repo = LocalGitRepo(name=name, work=work, origin=origin, author_email=author_email)
    tree = dict(files if files is not None else SAMPLE_TREE)
    readme = {"README.md": f"# {name}\n\nA small service used by the test suite.\n"}
    first = dict(list(tree.items())[: len(tree) // 2]) | readme
    git(work, "symbolic-ref", "HEAD", "refs/heads/main")
    repo.commit(first, "Start the service")
    repo.commit(tree, "Add the remaining modules")
    git(work, "checkout", "-q", "-b", "develop")
    git(work, "push", "-q", "origin", "develop")
    git(work, "checkout", "-q", "main")
    git(origin, "symbolic-ref", "HEAD", "refs/heads/main")
    git(work, "remote", "set-head", "origin", "main")
    return repo
