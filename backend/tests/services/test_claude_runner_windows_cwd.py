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

"""Native-Windows support in the spawn-cwd allowlist (``_validate_working_dir``).

The POSIX allowlist never matches a Windows drive-letter path, so Windows adds
roots for the data dir / temp / home and normalizes backslashes. These tests
drive the win32 branch on any host by mocking ``sys.platform`` and dropping the
POSIX roots so only the Windows roots can match — while keeping the security
guards (outside-root, traversal, credential-dir) intact.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

from app.services import claude_runner
from app.services.claude_runner import (
    NO_REPO_CONTEXT,
    _validate_working_dir,
    _windows_cwd_roots,
)


def test_windows_roots_empty_off_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    assert _windows_cwd_roots() == ()


def test_windows_roots_are_normalized(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    roots = _windows_cwd_roots()
    assert roots
    for root in roots:
        assert root.endswith("/")
        assert "\\" not in root
    temp_root = tempfile.gettempdir().replace("\\", "/").rstrip("/") + "/"
    assert temp_root in roots


def _win32_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pretend to be Windows AND drop the POSIX roots, so only Windows roots match."""
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(claude_runner, "_ALLOWED_CWD_ROOTS", ())


def test_accepts_backslash_path_under_a_windows_root(monkeypatch: pytest.MonkeyPatch) -> None:
    _win32_only(monkeypatch)
    real = Path(tempfile.mkdtemp()) / "acme" / "web"
    real.mkdir(parents=True)
    # Feed it the way Windows would — backslash separators.
    windows_input = str(real).replace("/", "\\")

    resolved = _validate_working_dir(windows_input)

    assert Path(resolved).resolve() == real.resolve()


def test_no_repo_context_scratch_dir_is_allowed_on_windows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The connection-test ping path (NO_REPO_CONTEXT) must validate on Windows."""
    _win32_only(monkeypatch)
    # Scratch dir lives under the system temp dir, which is a Windows root.
    resolved = _validate_working_dir(NO_REPO_CONTEXT)
    assert Path(resolved).name == "bodhiorchard-no-repo"


def test_rejects_windows_path_outside_every_root(monkeypatch: pytest.MonkeyPatch) -> None:
    _win32_only(monkeypatch)
    with pytest.raises(ValueError, match="not under an allowed root"):
        _validate_working_dir("C:\\Windows\\System32")


def test_rejects_windows_traversal(monkeypatch: pytest.MonkeyPatch) -> None:
    _win32_only(monkeypatch)
    evil = str(Path(tempfile.gettempdir()) / "acme" / ".." / "escape").replace("/", "\\")
    with pytest.raises(ValueError, match="path-traversal"):
        _validate_working_dir(evil)


def test_rejects_windows_credential_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    _win32_only(monkeypatch)
    cred = str(Path.home() / ".ssh").replace("/", "\\")
    with pytest.raises(ValueError, match="credential dir"):
        _validate_working_dir(cred)
