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

"""Cross-platform dev server launcher.

``npm run dev:backend`` runs this instead of invoking the ``uvicorn`` CLI
directly, so the ``reload`` decision can be made in code, per platform.

On native Windows, uvicorn's own ``--reload`` forces a ``SelectorEventLoop``
in the reloaded worker process, regardless of the ``WindowsProactorEventLoopPolicy``
set in ``app.core.event_loop`` — uvicorn's loop_factory (see
``uvicorn/loops/asyncio.py``) returns ``SelectorEventLoop`` unconditionally
whenever reload or multiple workers are configured, bypassing the event-loop
policy entirely. ``SelectorEventLoop`` can't spawn subprocesses, so every
``asyncio.create_subprocess_exec`` call (git clone, AI CLI runs, the setup
wizard's CLI version check) crashes with ``NotImplementedError``.

Disabling ``reload`` on Windows sidesteps that path so uvicorn gets a real
``ProactorEventLoop``. macOS/Linux aren't affected by this uvicorn behavior,
so they keep hot-reload.
"""

import sys

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=sys.platform != "win32",
    )
