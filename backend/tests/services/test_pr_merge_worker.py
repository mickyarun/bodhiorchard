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

"""Unit tests for the PR-merge Redis-stream worker.

The worker glues five moving parts:

* :func:`publish_pr_merge_delivery` — webhook entry XADD + registry SADD.
* :func:`recover_orphans_at_startup` — re-publishes ``running`` /
  ``pending`` rows at boot.
* :func:`_ensure_group` — idempotent XGROUP CREATE that swallows
  ``BUSYGROUP``.
* :func:`_process_message` — drives one delivery through the status
  state machine (``running → done`` / ``failed``) + XACKs.
* :func:`_supervise` — polls the registry SET and spawns consumers.

Each test stubs the Redis client + DB session so the assertions cover
shape and ordering, not real I/O.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from redis.exceptions import ResponseError

from app.models.webhook_log import WebhookDeliveryStatus
from app.services import pr_merge_worker as mod

# --- Helpers ----------------------------------------------------------------


def _fake_redis(*, smembers: list[str] | None = None) -> MagicMock:
    """Build a minimal Redis stand-in covering the methods the worker
    actually calls.

    redis-py's async pipeline has a quirk: command methods on the
    pipeline are *synchronous* (they queue commands locally) while
    ``execute()`` is async. The fake mirrors this so the assertions
    can use ``assert_called_*`` for queued commands and
    ``assert_awaited_*`` for execute. ``redis.pipe`` is attached to
    the parent so tests can introspect after the context exits.
    """
    redis = MagicMock()
    redis.xack = AsyncMock(return_value=1)
    redis.xgroup_create = AsyncMock()
    redis.smembers = AsyncMock(return_value=set(smembers or []))
    redis.xreadgroup = AsyncMock(return_value=[])

    pipe = MagicMock()
    pipe.sadd = MagicMock(return_value=pipe)
    pipe.xadd = MagicMock(return_value=pipe)
    pipe.execute = AsyncMock(return_value=[1, "0-0"])

    class _PipeCtx:
        async def __aenter__(self) -> Any:
            return pipe

        async def __aexit__(self, *_a: Any) -> None:
            return None

    redis.pipeline = MagicMock(return_value=_PipeCtx())
    redis.pipe = pipe  # expose for test assertions after the context exits
    return redis


class _FakeLog:
    """Stand-in for a WebhookLog row in orphan-recovery tests."""

    def __init__(
        self,
        *,
        delivery_id: str,
        org_id: uuid.UUID,
        repo_id: uuid.UUID | None,
        payload: dict[str, Any] | None,
        status: WebhookDeliveryStatus,
    ) -> None:
        self.delivery_id = delivery_id
        self.org_id = org_id
        self.repo_id = repo_id
        self.payload = payload
        self.status = status


# --- publish_pr_merge_delivery ----------------------------------------------


@pytest.mark.asyncio
async def test_publish_pipelines_sadd_and_xadd(monkeypatch: pytest.MonkeyPatch) -> None:
    """Both registry SADD and stream XADD must land in one pipeline so
    a partial write can't leave the registry stale."""
    redis = _fake_redis()

    async def _get_redis() -> Any:
        return redis

    monkeypatch.setattr(mod, "get_redis", _get_redis)
    org_id = uuid.uuid4()
    repo_id = uuid.uuid4()

    ok = await mod.publish_pr_merge_delivery(org_id=org_id, repo_id=repo_id, delivery_id="del-1")

    assert ok is True
    redis.pipe.sadd.assert_called_once_with(mod.REGISTRY_KEY, f"{org_id}:{repo_id}")
    redis.pipe.xadd.assert_called_once_with(
        f"{mod.STREAM_KEY_PREFIX}:{org_id}:{repo_id}",
        {mod.XADD_FIELD_DELIVERY_ID: "del-1"},
    )
    redis.pipe.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_publish_returns_false_when_redis_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No Redis → log + return False; orphan recovery covers it next boot."""

    async def _get_redis() -> Any:
        return None

    monkeypatch.setattr(mod, "get_redis", _get_redis)
    ok = await mod.publish_pr_merge_delivery(
        org_id=uuid.uuid4(), repo_id=uuid.uuid4(), delivery_id="del-1"
    )
    assert ok is False


# --- Orphan recovery --------------------------------------------------------


@pytest.mark.asyncio
async def test_recover_orphans_republishes_running_and_pending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Both ``running`` (mid-handler crash) and ``pending`` (lost XADD)
    rows must be republished so the consumer picks them up.
    """
    redis = _fake_redis()
    org_id = uuid.uuid4()
    repo_id = uuid.uuid4()
    running = _FakeLog(
        delivery_id="r1",
        org_id=org_id,
        repo_id=repo_id,
        payload={"pr_number": 1},
        status=WebhookDeliveryStatus.RUNNING,
    )
    pending = _FakeLog(
        delivery_id="p1",
        org_id=org_id,
        repo_id=repo_id,
        payload={"pr_number": 2},
        status=WebhookDeliveryStatus.PENDING,
    )

    class _FakeRepo:
        def __init__(self, _db: Any) -> None:
            pass

        async def list_in_status(self, status: WebhookDeliveryStatus) -> list[_FakeLog]:
            if status == WebhookDeliveryStatus.RUNNING:
                return [running]
            if status == WebhookDeliveryStatus.PENDING:
                return [pending]
            return []

    class _FakeSession:
        async def __aenter__(self) -> Any:
            return object()

        async def __aexit__(self, *_a: Any) -> None:
            return None

    monkeypatch.setattr(mod, "WebhookLogRepository", _FakeRepo)
    monkeypatch.setattr(mod, "AsyncSessionLocal", lambda: _FakeSession())

    count = await mod.recover_orphans_at_startup(redis=redis)

    assert count == 2
    # Both rows pipelined a SADD + XADD; the call count tracks both.
    assert redis.pipe.sadd.call_count == 2
    assert redis.pipe.xadd.call_count == 2


@pytest.mark.asyncio
async def test_recover_orphans_marks_unreplayable_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A row with no repo_id/payload can't be republished — flip to FAILED."""
    redis = _fake_redis()
    bad = _FakeLog(
        delivery_id="bad",
        org_id=uuid.uuid4(),
        repo_id=None,
        payload=None,
        status=WebhookDeliveryStatus.RUNNING,
    )

    class _FakeRepoList:
        def __init__(self, _db: Any) -> None:
            pass

        async def list_in_status(self, status: WebhookDeliveryStatus) -> list[_FakeLog]:
            return [bad] if status == WebhookDeliveryStatus.RUNNING else []

    class _FakeSession:
        async def __aenter__(self) -> Any:
            return object()

        async def __aexit__(self, *_a: Any) -> None:
            return None

    fail_updates: list[dict[str, Any]] = []

    class _FailMarker:
        def __init__(self, _db: Any) -> None:
            pass

        async def update_status(self, **kw: Any) -> None:
            fail_updates.append(kw)

    # First instantiation is for list_in_status, second is for _mark_unreplayable_failed.
    calls = {"count": 0}

    def _factory(db: Any) -> Any:
        calls["count"] += 1
        return _FakeRepoList(db) if calls["count"] == 1 else _FailMarker(db)

    monkeypatch.setattr(mod, "WebhookLogRepository", _factory)

    def _session() -> Any:
        # _mark_unreplayable_failed awaits db.commit(); the AsyncMock
        # supplies an awaitable so the context yields cleanly.
        ctx_inner = MagicMock()
        ctx_inner.commit = AsyncMock(return_value=None)

        class _Wrap:
            async def __aenter__(self) -> Any:
                return ctx_inner

            async def __aexit__(self, *_a: Any) -> None:
                return None

        return _Wrap()

    monkeypatch.setattr(mod, "AsyncSessionLocal", _session)

    count = await mod.recover_orphans_at_startup(redis=redis)
    assert count == 0  # Nothing republished
    assert fail_updates and fail_updates[0]["status"] == WebhookDeliveryStatus.FAILED


# --- _process_message lifecycle --------------------------------------------


@pytest.mark.asyncio
async def test_process_message_happy_path_runs_handler_and_acks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Happy path: running → done → XACK."""
    redis = _fake_redis()
    status_log: list[tuple[str, Any, dict[str, Any]]] = []

    async def _set_status(
        delivery_id: str,
        status: Any,
        *,
        error: str | None = None,
        bump_attempts: bool = False,
    ) -> None:
        status_log.append((delivery_id, status, {"error": error, "bump_attempts": bump_attempts}))

    monkeypatch.setattr(mod, "_set_status", _set_status)
    handler_calls: list[str] = []

    async def _handler(delivery_id: str) -> None:
        handler_calls.append(delivery_id)

    await mod._process_message(
        redis=redis,
        handler=_handler,
        stream="pr-merge:o:r",
        message_id="0-1",
        fields={mod.XADD_FIELD_DELIVERY_ID: "del-1"},
    )

    assert handler_calls == ["del-1"]
    # RUNNING with bump, then DONE without.
    assert status_log[0][1] == WebhookDeliveryStatus.RUNNING
    assert status_log[0][2]["bump_attempts"] is True
    assert status_log[1][1] == WebhookDeliveryStatus.DONE
    redis.xack.assert_awaited_once_with("pr-merge:o:r", mod.CONSUMER_GROUP, "0-1")


@pytest.mark.asyncio
async def test_process_message_handler_exception_flips_to_failed_and_acks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A handler exception lands in status=failed AND still XACKs.

    Re-processing a failed message would loop forever (the cause is in
    the row, not in Redis). Operator-driven recovery flips the row
    back to ``pending`` and the orphan-recovery path republishes it on
    next boot.
    """
    redis = _fake_redis()
    status_log: list[tuple[str, Any, dict[str, Any]]] = []

    async def _set_status(
        delivery_id: str,
        status: Any,
        *,
        error: str | None = None,
        bump_attempts: bool = False,
    ) -> None:
        status_log.append((delivery_id, status, {"error": error}))

    monkeypatch.setattr(mod, "_set_status", _set_status)

    async def _handler(_did: str) -> None:
        raise RuntimeError("kaboom")

    await mod._process_message(
        redis=redis,
        handler=_handler,
        stream="pr-merge:o:r",
        message_id="0-1",
        fields={mod.XADD_FIELD_DELIVERY_ID: "del-2"},
    )

    failed_entry = [s for s in status_log if s[1] == WebhookDeliveryStatus.FAILED]
    assert failed_entry, "must transition to FAILED on handler error"
    assert "kaboom" in (failed_entry[0][2]["error"] or "")
    redis.xack.assert_awaited_once_with("pr-merge:o:r", mod.CONSUMER_GROUP, "0-1")


@pytest.mark.asyncio
async def test_process_message_missing_delivery_id_acks_and_does_not_call_handler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A malformed message must not stall the consumer — ack + log + move on."""
    redis = _fake_redis()
    handler_calls: list[str] = []

    async def _handler(d: str) -> None:
        handler_calls.append(d)

    await mod._process_message(
        redis=redis,
        handler=_handler,
        stream="pr-merge:o:r",
        message_id="0-1",
        fields={},  # ← no delivery_id field
    )

    assert handler_calls == []
    redis.xack.assert_awaited_once()


# --- _ensure_group ----------------------------------------------------------


@pytest.mark.asyncio
async def test_ensure_group_swallows_busygroup() -> None:
    """``BUSYGROUP Consumer Group name already exists`` is the expected
    race when two consumers race to create the group; must be silent.
    """
    redis = _fake_redis()
    redis.xgroup_create = AsyncMock(side_effect=ResponseError("BUSYGROUP exists"))
    await mod._ensure_group(redis=redis, key="pr-merge:o:r")
    # No exception escaped.


@pytest.mark.asyncio
async def test_ensure_group_reraises_other_response_errors() -> None:
    """Any non-BUSYGROUP error must surface — silent swallow would mask
    real config issues.
    """
    redis = _fake_redis()
    redis.xgroup_create = AsyncMock(side_effect=ResponseError("WRONGTYPE Operation"))
    with pytest.raises(ResponseError):
        await mod._ensure_group(redis=redis, key="pr-merge:o:r")


# --- Registry parsing -------------------------------------------------------


def test_registry_member_round_trip() -> None:
    """Round-trip: build member → parse it back to original UUIDs."""
    org_id = uuid.uuid4()
    repo_id = uuid.uuid4()
    member = mod._registry_member(org_id, repo_id)
    parsed = mod._parse_registry_member(member)
    assert parsed == (org_id, repo_id)


def test_parse_registry_member_returns_none_on_garbage() -> None:
    """A corrupted registry entry must not blow up the supervisor."""
    assert mod._parse_registry_member("not-a-uuid:also-not") is None
    assert mod._parse_registry_member("only-one-part") is None


# --- Supervisor -------------------------------------------------------------


@pytest.mark.asyncio
async def test_supervisor_spawns_one_consumer_per_member(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The supervisor's first tick should spawn exactly one consumer
    per registry member, then idempotently NOT respawn on later ticks.
    """
    org_id = uuid.uuid4()
    repo_id_a = uuid.uuid4()
    repo_id_b = uuid.uuid4()
    redis = _fake_redis(smembers=[f"{org_id}:{repo_id_a}", f"{org_id}:{repo_id_b}"])

    spawned: list[tuple[uuid.UUID, uuid.UUID]] = []

    async def _fake_consume(
        *,
        redis: Any,
        handler: Any,
        stop: asyncio.Event,
        org_id: uuid.UUID,
        repo_id: uuid.UUID,
    ) -> None:
        spawned.append((org_id, repo_id))
        await stop.wait()

    monkeypatch.setattr(mod, "_consume_stream", _fake_consume)
    monkeypatch.setattr(mod, "SUPERVISOR_POLL_SECONDS", 0.05)

    stop = asyncio.Event()
    consumers: dict[str, asyncio.Task[None]] = {}

    sup = asyncio.create_task(
        mod._supervise(redis=redis, handler=lambda _d: None, stop=stop, consumers=consumers)
    )
    # Give the supervisor a couple of polls.
    await asyncio.sleep(0.2)
    stop.set()
    await sup
    for t in consumers.values():
        t.cancel()
    await asyncio.gather(*consumers.values(), return_exceptions=True)

    # Exactly two consumers spawned, one per registry member.
    assert len(spawned) == 2
    assert (org_id, repo_id_a) in spawned
    assert (org_id, repo_id_b) in spawned
