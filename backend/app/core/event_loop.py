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
