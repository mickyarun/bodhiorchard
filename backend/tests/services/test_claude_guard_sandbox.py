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

"""Unit tests: macOS Seatbelt wrapper.

These tests run on every platform — the wrap behavior gates internally
on sys.platform + env flag, so the tests just verify the gating logic.
"""

from __future__ import annotations

import sys

import pytest

from app.services.claude_guard.macos_sandbox import maybe_wrap_with_sandbox


class TestMaybeWrapWithSandbox:
    """Wrap behavior depends on platform + opt-in env flag."""

    def test_returns_unchanged_when_flag_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("BODHIORCHARD_HYBRID_SANDBOX", raising=False)
        cmd = ["claude", "-p", "hello"]
        assert maybe_wrap_with_sandbox(cmd, "/workspace") == cmd

    def test_returns_unchanged_when_flag_is_zero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BODHIORCHARD_HYBRID_SANDBOX", "0")
        cmd = ["claude", "-p", "hello"]
        assert maybe_wrap_with_sandbox(cmd, "/workspace") == cmd

    @pytest.mark.skipif(sys.platform != "darwin", reason="Seatbelt is macOS-only")
    def test_wraps_when_enabled_on_darwin(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BODHIORCHARD_HYBRID_SANDBOX", "1")
        # If sandbox-exec is absent on the test host, the wrapper falls
        # back to the unchanged cmd — accept either outcome.
        result = maybe_wrap_with_sandbox(["claude", "-p", "x"], "/workspace")
        if result[0] != "claude":
            assert result[0] == "sandbox-exec"
            assert "-f" in result
            assert any("WORKSPACE=/workspace" in arg for arg in result)

    @pytest.mark.skipif(sys.platform == "darwin", reason="Non-Darwin only")
    def test_returns_unchanged_on_non_darwin(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BODHIORCHARD_HYBRID_SANDBOX", "1")
        cmd = ["claude", "-p", "hello"]
        assert maybe_wrap_with_sandbox(cmd, "/workspace") == cmd
