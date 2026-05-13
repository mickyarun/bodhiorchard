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

"""Tests for the ``safe_join`` path-traversal sanitiser."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.core.paths import PathTraversalError, safe_join


def test_safe_join_simple_relative(tmp_path: Path) -> None:
    """Normal nested path resolves cleanly under the root."""
    result = safe_join(tmp_path, "evidence/file.png")
    assert result == (tmp_path / "evidence" / "file.png").resolve()
    assert result.is_relative_to(tmp_path.resolve())


def test_safe_join_accepts_string_root(tmp_path: Path) -> None:
    """Root may be passed as either ``str`` or ``Path``."""
    assert safe_join(str(tmp_path), "a/b") == safe_join(tmp_path, "a/b")


@pytest.mark.parametrize(
    "payload",
    [
        "../escape.txt",
        "evidence/../../escape.txt",
        "a/b/../../../etc/passwd",
        "/absolute/path",  # leading-slash makes Path() discard the root
        "/etc/passwd",
    ],
)
def test_safe_join_rejects_traversal(tmp_path: Path, payload: str) -> None:
    """``..``-traversal and absolute paths are rejected, even when they would resolve outside."""
    with pytest.raises(PathTraversalError):
        safe_join(tmp_path, payload)


def test_safe_join_rejects_empty_relative(tmp_path: Path) -> None:
    """Empty ``relative`` is a misuse — callers wanting the root should pass ``root`` directly."""
    with pytest.raises(PathTraversalError, match="must not be empty"):
        safe_join(tmp_path, "")


def test_safe_join_rejects_symlink_escape(tmp_path: Path) -> None:
    """A symlink that points outside the root is caught by ``.resolve()``."""
    outside = tmp_path.parent / "outside_target"
    outside.mkdir(exist_ok=True)
    try:
        inside_link = tmp_path / "escape_link"
        os.symlink(outside, inside_link)
        with pytest.raises(PathTraversalError):
            safe_join(tmp_path, "escape_link/file.txt")
    finally:
        if outside.exists():
            for child in outside.iterdir():
                child.unlink()
            outside.rmdir()


def test_safe_join_rejects_sibling_with_shared_prefix(tmp_path: Path) -> None:
    """A ``startswith``-style check would have allowed ``/root_evil`` when root is ``/root``.

    ``Path.is_relative_to`` uses path component boundaries and correctly
    rejects this case. The test guards against regressing back to a
    string-prefix check.
    """
    root = tmp_path / "root"
    root.mkdir()
    sibling_evil = tmp_path / "root_evil"
    sibling_evil.mkdir()
    (sibling_evil / "loot").write_text("x")

    with pytest.raises(PathTraversalError):
        safe_join(root, "../root_evil/loot")
