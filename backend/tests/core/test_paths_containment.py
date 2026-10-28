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

"""Tests for the resolved-path containment helpers used before ``rmtree``."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.paths import is_strictly_under, rmtree_strictly_under


@pytest.fixture
def root(tmp_path: Path) -> Path:
    base = tmp_path / "root"
    (base / "org" / "repo").mkdir(parents=True)
    (tmp_path / "rootsibling").mkdir()
    (tmp_path / "outside").mkdir()
    return base


def test_nested_paths_are_under(root: Path) -> None:
    assert is_strictly_under(root / "org", root)
    assert is_strictly_under(root / "org" / "repo", root)
    assert is_strictly_under(str(root / "org"), str(root))


@pytest.mark.parametrize(
    "relative",
    ["", ".", "org/..", "org/../..", "..", "../rootsibling", "../outside"],
)
def test_the_parent_itself_and_escapes_are_not_under(root: Path, relative: str) -> None:
    assert not is_strictly_under(root / relative, root)


def test_a_symlink_is_judged_by_where_it_lands(root: Path) -> None:
    (root / "org" / "escape").symlink_to(root.parent / "outside")
    (root / "org" / "loop").symlink_to(root)
    assert not is_strictly_under(root / "org" / "escape", root)
    assert not is_strictly_under(root / "org" / "loop", root)


def test_rmtree_deletes_only_inside(root: Path) -> None:
    assert rmtree_strictly_under(root / "org" / "..", root) is False
    assert rmtree_strictly_under(root / "..", root) is False
    assert (root / "org" / "repo").is_dir()
    assert (root.parent / "outside").is_dir()

    assert rmtree_strictly_under(root / "org" / "repo", root) is True
    assert not (root / "org" / "repo").exists()
    assert (root / "org").is_dir()


def test_rmtree_refuses_a_symlink_even_inside(root: Path) -> None:
    link = root / "org" / "alias"
    link.symlink_to(root / "org" / "repo")
    assert rmtree_strictly_under(link, root) is False
    assert link.is_symlink()
    assert (root / "org" / "repo").is_dir()
