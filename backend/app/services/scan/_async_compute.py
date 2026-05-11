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

"""Instrumented ``asyncio.to_thread`` wrapper for CPU-bound scan stages.

Scan stages have a few hot paths that are pure-Python CPU work
(NetworkX traversals, regex sweeps, dedupe loops). Running them on
the event loop thread blocks unrelated requests like
``GET /v1/setup/status`` during a bulk-onboard. The fix is to push
each blocking chunk into ``asyncio.to_thread``; this helper centralises
that pattern and emits a structlog event so the next session can rank
stages by p99 runtime.

Single seam, single event name — keeps the rank-and-fix loop simple.

Note on Python version: ``contextvars`` propagation across
``asyncio.to_thread`` requires Python 3.12+. The backend pins 3.12,
so structlog bound context (``org_id``, ``scan_id``, …) survives the
thread boundary. If the project ever drops to 3.11, threaded-stage
logs will lose their bound context — revisit this module first.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable

import structlog

logger = structlog.get_logger(__name__)


async def to_thread_with_metric[**P, R](
    stage: str,
    fn: Callable[P, R],
    /,
    *args: P.args,
    **kwargs: P.kwargs,
) -> R:
    """Run ``fn`` in the default thread executor and emit a runtime metric.

    Records two timings:

    - ``runtime_ms`` — wall-clock time spent inside the threaded call.
    - ``loop_lag_ms`` — gap between scheduling the await and the loop
      resuming after it. A high lag with low runtime means the thread
      pool was queue-bound, not the function itself.

    Use this in place of bare ``asyncio.to_thread`` for any scan-stage
    CPU chunk worth measuring.
    """
    loop = asyncio.get_running_loop()
    schedule_t = loop.time()
    work_start = time.perf_counter()
    try:
        return await asyncio.to_thread(fn, *args, **kwargs)
    finally:
        work_end = time.perf_counter()
        resume_t = loop.time()
        logger.info(
            "cpu_stage_thread_runtime",
            stage=stage,
            runtime_ms=round((work_end - work_start) * 1000, 2),
            loop_lag_ms=round((resume_t - schedule_t) * 1000 - (work_end - work_start) * 1000, 2),
        )
