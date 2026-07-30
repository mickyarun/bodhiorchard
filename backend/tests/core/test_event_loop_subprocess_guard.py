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

"""Detecting a loop that cannot spawn subprocesses, before anything needs one.

uvicorn installs ``WindowsSelectorEventLoopPolicy`` whenever ``--reload`` or
``--workers`` is set, and creates the loop before importing this app — so the
Proactor policy set at import time never takes effect. Every git call, scan and
agent run then raises ``NotImplementedError`` from inside a request, which the
setup wizard reported as a problem with the path the user had typed. One
evaluator went looking for a missing ``.git`` in a checkout that had one.

Saying it at boot is the whole point: by the time the request fails, the cause
is several layers away from the symptom.
"""

import asyncio
import sys
from unittest.mock import MagicMock, patch

import pytest

from app.core.event_loop import (
    configure_event_loop_policy,
    loop_cannot_spawn_subprocesses,
    warn_if_subprocess_unsupported,
)

_MOD = "app.core.event_loop"


@pytest.mark.asyncio
async def test_non_windows_is_never_flagged() -> None:
    """Selector loops spawn subprocesses fine off Windows — flagging them would
    fire this warning on every macOS and Linux boot."""
    with patch(f"{_MOD}.sys.platform", "linux"):
        assert loop_cannot_spawn_subprocesses() is False


@pytest.mark.asyncio
async def test_windows_selector_loop_is_flagged() -> None:
    """The uvicorn --reload case: a Selector loop on Windows."""
    with (
        patch(f"{_MOD}.sys.platform", "win32"),
        patch(f"{_MOD}.asyncio.get_running_loop", return_value=MagicMock()),
    ):
        assert loop_cannot_spawn_subprocesses() is True


@pytest.mark.asyncio
async def test_windows_proactor_loop_is_not_flagged() -> None:
    """The correctly-launched case must stay silent, or the warning is noise."""
    proactor = MagicMock(spec=asyncio.ProactorEventLoop if sys.platform == "win32" else object)
    with (
        patch(f"{_MOD}.sys.platform", "win32"),
        patch(f"{_MOD}.asyncio.get_running_loop", return_value=proactor),
        patch(f"{_MOD}.asyncio.ProactorEventLoop", type(proactor), create=True),
    ):
        assert loop_cannot_spawn_subprocesses() is False


def test_no_running_loop_is_not_flagged() -> None:
    """Called outside a loop (imports, tooling) it must answer, not raise."""
    with patch(f"{_MOD}.sys.platform", "win32"):
        assert loop_cannot_spawn_subprocesses() is False


@pytest.mark.asyncio
async def test_the_warning_names_the_remedy() -> None:
    """A warning that only says 'unsupported' leaves the reader where they
    started — it has to carry the command that fixes it."""
    with (
        patch(f"{_MOD}.loop_cannot_spawn_subprocesses", return_value=True),
        patch(f"{_MOD}.logger") as log,
    ):
        warn_if_subprocess_unsupported()

    remedy = log.error.call_args.kwargs["remedy"]
    assert "dev_server.py" in remedy
    assert "--reload" in remedy


@pytest.mark.asyncio
async def test_nothing_is_logged_on_a_healthy_loop() -> None:
    with (
        patch(f"{_MOD}.loop_cannot_spawn_subprocesses", return_value=False),
        patch(f"{_MOD}.logger") as log,
    ):
        warn_if_subprocess_unsupported()

    log.error.assert_not_called()


def test_configuring_the_policy_is_a_no_op_off_windows() -> None:
    """It runs unconditionally at import, so it must not disturb other platforms."""
    before = asyncio.get_event_loop_policy()
    with patch(f"{_MOD}.sys.platform", "linux"):
        configure_event_loop_policy()

    assert asyncio.get_event_loop_policy() is before
