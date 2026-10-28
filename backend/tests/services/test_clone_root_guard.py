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

"""``in_clone_root`` and ``safe_join``: the two path barriers, unit by unit.

The endpoint suites exercise these through HTTP; this pins the edges of
each predicate on its own, so a regression points at the helper.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.config import settings as app_settings
from app.core.paths import PathTraversalError, safe_join
from app.services.directory_listing import in_clone_root


@pytest.fixture
def repos_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setattr(app_settings.storage, "data_dir", str(tmp_path.resolve() / "data"))
    path = app_settings.storage.repos_dir
    path.mkdir(parents=True)
    return path


class TestInCloneRoot:
    """Whether a resolved path is inside the shared clone root."""

    def test_the_root_and_anything_under_it(self, repos_dir: Path) -> None:
        assert in_clone_root(str(repos_dir))
        assert in_clone_root(str(repos_dir / "org" / "repo" / "src"))

    def test_a_different_case_still_counts(self, repos_dir: Path) -> None:
        """A case-insensitive volume opens this spelling as the clone root."""
        assert in_clone_root(str(repos_dir.parent / "REPOS" / "org"))

    @pytest.mark.parametrize("name", ["repos2", "repos-old", "repo"])
    def test_a_sibling_sharing_a_prefix_does_not(self, repos_dir: Path, name: str) -> None:
        assert not in_clone_root(str(repos_dir.parent / name / "org"))

    def test_the_parent_and_unrelated_paths_do_not(self, repos_dir: Path) -> None:
        assert not in_clone_root(str(repos_dir.parent))
        assert not in_clone_root("/")

    def test_a_relative_path_never_matches(self, repos_dir: Path) -> None:
        """Callers pass realpath output; a relative string is an unrelated root."""
        assert not in_clone_root("repos/org")


class TestSafeJoinEdges:
    """Edges of ``safe_join`` the main suite does not cover."""

    def test_unicode_segments_stay_inside(self, tmp_path: Path) -> None:
        result = safe_join(tmp_path, "café/日本語.png")
        assert result == tmp_path.resolve() / "café" / "日本語.png"

    def test_dot_is_the_root_itself(self, tmp_path: Path) -> None:
        assert safe_join(tmp_path, ".") == tmp_path.resolve()

    def test_a_symlink_that_stays_inside_is_followed(self, tmp_path: Path) -> None:
        (tmp_path / "real").mkdir()
        os.symlink(tmp_path / "real", tmp_path / "link")
        assert safe_join(tmp_path, "link/a.txt") == tmp_path.resolve() / "real" / "a.txt"

    def test_a_root_that_is_itself_a_symlink(self, tmp_path: Path) -> None:
        """Both sides are resolved, so a linked root still contains its children."""
        (tmp_path / "real").mkdir()
        os.symlink(tmp_path / "real", tmp_path / "root-link")
        assert safe_join(tmp_path / "root-link", "x") == tmp_path.resolve() / "real" / "x"

    def test_a_very_long_relative_path_is_only_joined(self, tmp_path: Path) -> None:
        """No filesystem call beyond realpath, so length alone is not an error."""
        deep = "/".join(["d" * 200] * 10)
        assert safe_join(tmp_path, deep).is_relative_to(tmp_path.resolve())

    @pytest.mark.parametrize("payload", ["..", "../", "a/../..", "./../x"])
    def test_climbing_out_by_one_level_is_refused(self, tmp_path: Path, payload: str) -> None:
        with pytest.raises(PathTraversalError):
            safe_join(tmp_path / "root", payload)
