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

"""Unit tests for ``app.scan.session`` — the only sanctioned session helper.

These tests don't touch a real database. ``with_session`` is exercised
via a stub ``AsyncSessionLocal`` so we can prove the commit-on-success
and rollback-on-exception contract without infrastructure overhead.
``gather_repos`` is tested with plain coroutines.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import pytest

from app.scan import session as sess


class _FakeSession:
    """Minimal stub of ``AsyncSession`` covering only the calls under test."""

    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False
        self.closed = False

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True

    async def __aenter__(self) -> _FakeSession:
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.closed = True


def _patch_session_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> list[_FakeSession]:
    """Replace ``AsyncSessionLocal`` with a factory tracking each created session."""
    sessions: list[_FakeSession] = []

    def factory() -> _FakeSession:
        s = _FakeSession()
        sessions.append(s)
        return s

    monkeypatch.setattr(sess, "AsyncSessionLocal", factory)
    return sessions


# ───────────────────────── with_session ─────────────────────────


async def test_with_session_commits_on_clean_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Happy path → session.commit() called, rollback never fires."""
    sessions = _patch_session_factory(monkeypatch)
    async with sess.with_session(uuid.uuid4()) as s:
        assert isinstance(s, _FakeSession)
    assert len(sessions) == 1
    assert sessions[0].committed is True
    assert sessions[0].rolled_back is False
    assert sessions[0].closed is True


async def test_with_session_rolls_back_on_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    """Phase raises → session.rollback() called, commit never fires, exception propagates."""
    sessions = _patch_session_factory(monkeypatch)

    class _BoomError(RuntimeError):
        pass

    with pytest.raises(_BoomError):
        async with sess.with_session(uuid.uuid4()):
            raise _BoomError("phase body raised")

    assert len(sessions) == 1
    assert sessions[0].committed is False
    assert sessions[0].rolled_back is True
    assert sessions[0].closed is True


# ───────────────────────── gather_repos ─────────────────────────


async def test_gather_repos_bounds_concurrent_executions() -> None:
    """At most ``max_concurrent`` coroutines should be in flight at once."""
    in_flight = 0
    peak = 0
    lock = asyncio.Lock()

    async def task(idx: int) -> int:
        nonlocal in_flight, peak
        async with lock:
            in_flight += 1
            peak = max(peak, in_flight)
        await asyncio.sleep(0.01)
        async with lock:
            in_flight -= 1
        return idx

    results = await sess.gather_repos(
        (task(i) for i in range(20)),
        max_concurrent=4,
    )
    assert results == list(range(20))
    assert peak <= 4, f"peak concurrency was {peak}, expected <= 4"


async def test_gather_repos_returns_exceptions_in_place() -> None:
    """Failing coroutines surface as exceptions in the result list, not via raise."""

    class _BoomError(RuntimeError):
        pass

    async def good(i: int) -> int:
        return i

    async def bad() -> int:
        raise _BoomError("nope")

    results = await sess.gather_repos(
        [good(1), bad(), good(2)],
        max_concurrent=2,
    )
    assert results[0] == 1
    assert isinstance(results[1], _BoomError)
    assert results[2] == 2


async def test_gather_repos_rejects_zero_concurrency() -> None:
    """``max_concurrent=0`` is a programming error — fail loudly, not silently hang."""
    with pytest.raises(ValueError, match="max_concurrent must be >= 1"):
        await sess.gather_repos([], max_concurrent=0)
