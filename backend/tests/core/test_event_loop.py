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

"""Tests for ``configure_event_loop_policy`` (Windows subprocess support)."""

import asyncio
import sys
from typing import Any

import pytest

from app.core.event_loop import configure_event_loop_policy


@pytest.mark.parametrize("platform", ["linux", "darwin"])
def test_noop_off_windows(monkeypatch: pytest.MonkeyPatch, platform: str) -> None:
    """Non-Windows loops already spawn subprocesses, so the policy is left alone."""
    monkeypatch.setattr(sys, "platform", platform)
    calls: list[Any] = []
    monkeypatch.setattr(asyncio, "set_event_loop_policy", lambda p: calls.append(p))

    configure_event_loop_policy()

    assert calls == []


def test_sets_proactor_policy_on_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    """On Windows the Proactor policy is installed so create_subprocess_exec works.

    ``WindowsProactorEventLoopPolicy`` only exists on Windows, so it is injected
    here to exercise the win32 branch on any host.
    """
    monkeypatch.setattr(sys, "platform", "win32")
    sentinel = object()
    monkeypatch.setattr(asyncio, "WindowsProactorEventLoopPolicy", lambda: sentinel, raising=False)
    captured: list[Any] = []
    monkeypatch.setattr(asyncio, "set_event_loop_policy", lambda p: captured.append(p))

    configure_event_loop_policy()

    assert captured == [sentinel]
