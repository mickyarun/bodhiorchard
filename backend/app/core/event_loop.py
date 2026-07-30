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

"""Event-loop policy configuration (Windows subprocess support)."""

import asyncio
import sys

import structlog

logger = structlog.get_logger(__name__)


def configure_event_loop_policy() -> None:
    """On Windows, force the Proactor event loop so asyncio can spawn subprocesses.

    ``asyncio.create_subprocess_exec`` — used for git clone, repo scanning, and
    every AI-agent CLI run — raises ``NotImplementedError`` on a
    ``SelectorEventLoop``. Only the ``ProactorEventLoop`` supports subprocesses
    on Windows, and while it is the CPython 3.8+ default, some Windows/uvicorn
    reload/worker configurations land on a Selector loop instead. Setting the
    policy here — at import time, before uvicorn creates the serving loop —
    makes the whole app subprocess-capable on Windows.

    No-op on macOS / Linux / Docker (their default loops already spawn
    subprocesses), so it is always safe to call unconditionally.
    """
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())


def loop_cannot_spawn_subprocesses() -> bool:
    """Whether the running loop will refuse ``create_subprocess_exec``.

    Only true on Windows, and only when something replaced the policy set above
    after it was applied. uvicorn does exactly that: ``asyncio_setup`` installs
    ``WindowsSelectorEventLoopPolicy`` whenever ``--reload`` or ``--workers``
    is used, and it creates the loop before importing this app — so the policy
    we set at import time is already too late to matter.
    """
    if sys.platform != "win32":
        return False
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return False
    # ``ProactorEventLoop`` is defined only on Windows — the attribute is absent
    # on macOS/Linux, so name it through getattr rather than dotted access. In
    # production the platform guard above means this line is only reached on
    # Windows, where the class exists; the fallback matters only when a test
    # simulates win32 on another OS, and an empty tuple makes ``isinstance``
    # answer False there, which is the "not a Proactor loop" case we report.
    proactor_cls = getattr(asyncio, "ProactorEventLoop", ())
    return not isinstance(loop, proactor_cls)


def warn_if_subprocess_unsupported() -> None:
    """Log a loud, actionable error when git and agent runs are going to fail.

    Every scan, clone and CLI agent run shells out. On a loop that cannot spawn
    subprocesses each of those raises ``NotImplementedError`` from deep inside a
    request, which surfaces as a 500 the UI then reports as a problem with the
    user's input — a Windows evaluator was sent looking for a missing ``.git``
    in a checkout that had one. Saying it once at boot, where the cause is
    still visible, costs nothing and stops that hunt before it starts.
    """
    if not loop_cannot_spawn_subprocesses():
        return
    logger.error(
        "event_loop_cannot_spawn_subprocesses",
        remedy=(
            "Run 'python backend\\dev_server.py' (or drop --reload). uvicorn's "
            "--reload and --workers force a SelectorEventLoop on Windows, which "
            "cannot spawn subprocesses — git, repository scans and agent runs "
            "will all fail with NotImplementedError until this is changed."
        ),
    )
