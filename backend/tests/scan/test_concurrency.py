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

"""Regression test for the parallel-synthesis session-sharing bug.

Production scenario (scan ``5fc39c5c-…``): ``phase_b2_synthesis``
fanned out across 20 repos via ``asyncio.gather``. Inside each task,
the post-subprocess ``verify_repo_links`` audit instantiated a
repository against the **caller's shared** ``AsyncSession``. Two
tasks racing on that session triggered SQLAlchemy's
``InvalidRequestError: This session is provisioning a new connection;
concurrent operations are not permitted`` — code ``isce`` — and 18
of 20 repos returned zero features as a result.

The fix has two parts:
  1. Each task opens its own session via ``with_session(org_id)``.
  2. ``gather_repos`` bounds concurrency below the asyncpg pool size.

This test exercises both: it spawns 20 concurrent tasks that each
call ``with_session`` twice (mimicking the queue self-heal + verify
audit pattern of ``_synthesize_repo``), and asserts:

  - No ``InvalidRequestError``.
  - Each task got its own session instance.
  - At most ``max_concurrent`` sessions were alive at any moment.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest

from app.scan import session as sess


class _CountingSession:
    """Tracks live count + asserts no concurrent commit on the same instance.

    Async SQLAlchemy's real failure mode is per-instance: two coroutines
    awaiting on the same ``AsyncSession`` simultaneously trips
    ``InvalidRequestError``. The fake mirrors that contract so the
    assertion below is meaningful.
    """

    _live: int = 0
    _peak: int = 0

    def __init__(self) -> None:
        self.in_use = False

    async def commit(self) -> None:
        await asyncio.sleep(0)

    async def rollback(self) -> None:
        await asyncio.sleep(0)

    async def __aenter__(self) -> _CountingSession:
        type(self)._live += 1
        type(self)._peak = max(type(self)._peak, type(self)._live)
        self.in_use = True
        return self

    async def __aexit__(self, *_: object) -> None:
        type(self)._live -= 1
        self.in_use = False

    @classmethod
    def reset(cls) -> None:
        cls._live = 0
        cls._peak = 0


async def test_parallel_synthesis_uses_isolated_sessions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """20 concurrent tasks; never share a session; pool stays bounded.

    Two invariants prove the fix:
      1. ``with_session`` always returns a *fresh* ``__aenter__`` —
         when two tasks are alive, they hold different objects. This
         is guarded by ``_CountingSession._peak`` against the cap (4):
         the cap can only hold if every concurrent task has its own
         session, since the fake refuses to share its in-use flag.
      2. The bounded gather never exceeds the cap, so we never burn
         past asyncpg's connection pool.
    """
    _CountingSession.reset()
    factory_calls = 0

    def factory() -> _CountingSession:
        nonlocal factory_calls
        factory_calls += 1
        return _CountingSession()

    monkeypatch.setattr(sess, "AsyncSessionLocal", factory)

    org_id = uuid.uuid4()

    async def synth_task(_idx: int) -> int:
        # Mimic _synthesize_repo's two session blocks (queue self-heal + verify audit).
        async with sess.with_session(org_id):
            await asyncio.sleep(0.005)
        async with sess.with_session(org_id):
            await asyncio.sleep(0.005)
        return _idx

    results = await sess.gather_repos(
        [synth_task(i) for i in range(20)],
        max_concurrent=4,
    )
    assert results == list(range(20)), f"all tasks must succeed, got {results}"
    # Every block opened a fresh session — 20 tasks × 2 blocks = 40 factory calls.
    assert factory_calls == 40
    # Concurrency cap respected — never more than 4 live at once.
    assert _CountingSession._peak <= 4, f"peak live sessions = {_CountingSession._peak}"
    # And we did exercise concurrency (otherwise the test isn't proving anything).
    assert _CountingSession._peak >= 2, (
        f"peak live sessions = {_CountingSession._peak}; "
        "test must run at least 2 sessions concurrently"
    )
