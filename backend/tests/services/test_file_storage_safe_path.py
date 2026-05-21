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

"""Tests for ``FileStorage._safe_local_path``'s traversal guard.

These tests target the path-injection sanitiser only — the S3 backend
and upload/download size+MIME guards already have coverage elsewhere.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.file_storage import FileStorage, FileStorageError


def _storage_at(local_dir: Path) -> FileStorage:
    """Build a ``FileStorage`` with its local-dir pointed at a tmp path."""
    storage = FileStorage()
    storage.use_s3 = False
    storage.local_dir = str(local_dir)
    return storage


def test_safe_local_path_resolves_under_root(tmp_path: Path) -> None:
    """A normal nested relative path stays inside the configured root."""
    storage = _storage_at(tmp_path)
    resolved = storage._safe_local_path("org-123/qa-evidence/tc-001/file.png")
    assert resolved.is_relative_to(tmp_path.resolve())


@pytest.mark.parametrize(
    "payload",
    [
        "../escape.txt",
        "org-123/../../escape.txt",
        "org-123/qa-evidence/../../../etc/passwd",
        "/etc/passwd",  # leading-slash bypass
    ],
)
def test_safe_local_path_rejects_traversal(tmp_path: Path, payload: str) -> None:
    """Path-traversal payloads raise ``FileStorageError`` with a clean message."""
    storage = _storage_at(tmp_path)
    with pytest.raises(FileStorageError, match="directory traversal"):
        storage._safe_local_path(payload)


def test_safe_local_path_rejects_shared_prefix_sibling(tmp_path: Path) -> None:
    """Reject siblings whose path string shares a prefix with the root.

    The old ``str.startswith`` check would have allowed ``/data/uploads_evil``
    when the root was ``/data/uploads``. ``Path.is_relative_to`` uses
    component boundaries and correctly rejects this case.
    """
    root = tmp_path / "uploads"
    root.mkdir()
    storage = _storage_at(root)

    sibling = tmp_path / "uploads_evil"
    sibling.mkdir()
    (sibling / "loot.txt").write_text("x")

    with pytest.raises(FileStorageError, match="directory traversal"):
        storage._safe_local_path("../uploads_evil/loot.txt")
