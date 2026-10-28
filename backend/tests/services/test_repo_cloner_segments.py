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

"""A dots-only owner, repo or slug never becomes a clone path segment.

``.`` and ``..`` pass a letters-digits-dots check, and joined under the
clone root they name the org folder or the root itself: a clone would
land on every org's clones, and a purge of ``..`` would delete them all.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from app.config import settings as app_settings
from app.services import repo_cloner


@pytest.fixture
def repos_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setattr(app_settings.storage, "data_dir", str(tmp_path / "data"))
    root = app_settings.storage.repos_dir
    for org in ("acme", "other-org"):
        (root / org / "widgets" / ".git").mkdir(parents=True)
    return root


@pytest.fixture
def git_calls(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    calls: list[list[str]] = []

    async def _never(args: list[str], **_: Any) -> tuple[int, str, str]:
        calls.append(args)
        return 0, "", ""

    monkeypatch.setattr(repo_cloner, "_run_git", _never)
    return calls


def _clones(root: Path) -> int:
    return sum(1 for _ in root.glob("*/*/.git"))


@pytest.mark.parametrize(
    ("url", "slug"),
    [
        ("https://github.com/acme/..", "acme"),
        ("https://github.com/acme/.", "acme"),
        ("https://github.com/acme/...", "acme"),
        ("git@github.com:../widgets.git", "acme"),
        ("https://github.com/acme/widgets", ".."),
    ],
)
async def test_clone_refuses_dot_segments_without_running_git(
    repos_dir: Path, git_calls: list[list[str]], url: str, slug: str
) -> None:
    result = await repo_cloner.clone_or_update(url, org_slug=slug)
    assert result.success is False
    assert result.error == "Invalid characters in owner, repo, or org slug."
    assert git_calls == []


@pytest.mark.parametrize("name", ["..", ".", "..."])
def test_purges_refuse_dot_segments_and_delete_nothing(repos_dir: Path, name: str) -> None:
    with pytest.raises(ValueError):
        repo_cloner.purge_repo_clones("acme", [name])
    with pytest.raises(ValueError):
        repo_cloner.purge_org_clones(name)
    assert _clones(repos_dir) == 2


async def test_names_with_dots_inside_are_still_fine(
    repos_dir: Path, git_calls: list[list[str]]
) -> None:
    result = await repo_cloner.clone_or_update(
        "https://github.com/acme.io/widgets.js", org_slug="acme"
    )
    assert result.success is True
    assert result.path == str(repos_dir / "acme" / "widgets.js")
    assert repo_cloner.purge_repo_clones("acme", [".github"]) == 0
