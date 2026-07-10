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

"""``create_scan`` degrades gracefully to a direct scan when Redis is down.

Re-scans are normally consumed by the PR-merge Redis-stream worker, which only
starts at boot when Redis is up. When Redis is unreachable we do NOT fail the
request — instead the re-scan repos are folded into a direct full scan (which
needs no Redis) so scanning keeps working. We also fall back to a direct scan
if Redis errors mid-enqueue.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from redis.exceptions import TimeoutError as RedisTimeoutError

from app.api.v1 import scans
from app.schemas.scan import StartScanRequest


async def test_rescan_degrades_to_direct_scan_when_redis_down(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Redis down → re-scan repo folded into a direct scan, no 503, no enqueue."""
    repo_id = uuid.uuid4()
    scan_id = uuid.uuid4()
    monkeypatch.setattr(scans, "_resolve_org_id", AsyncMock(return_value=uuid.uuid4()))
    monkeypatch.setattr(scans, "_split_by_scan_history", AsyncMock(return_value=([], [repo_id])))
    monkeypatch.setattr(scans, "get_redis", AsyncMock(return_value=None))
    enqueue = AsyncMock(return_value="rescan-x")
    monkeypatch.setattr(scans, "enqueue_rescan_delivery", enqueue)
    start = AsyncMock(return_value=scan_id)
    monkeypatch.setattr(scans, "start_scan", start)

    resp = await scans.create_scan(
        StartScanRequest(repo_ids=[repo_id]), current_user=MagicMock(), db=MagicMock()
    )

    # No 503: the re-scan ran as a direct scan instead.
    assert resp.scan_id == scan_id
    assert resp.rescan_delivery_ids == []
    enqueue.assert_not_awaited()  # never queued a delivery that would sit pending
    # The re-scan repo was passed to the direct scan pipeline.
    assert start.await_args.kwargs["repo_ids"] == [repo_id]


async def test_first_scan_dispatched_even_if_rescan_enqueue_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A never-scanned repo must still be scanned when a co-requested re-scan's
    enqueue errors mid-request (Redis died after the up-front check).

    The direct scan is dispatched BEFORE the enqueue loop, so the re-scan
    error can't strand it. The re-scan itself is deferred — its durable
    ``webhook_logs`` row is replayed by boot-time orphan-recovery — so the
    request still succeeds (no 500) rather than losing the first scan.
    """
    first_id, rescan_id = uuid.uuid4(), uuid.uuid4()
    scan_id = uuid.uuid4()
    monkeypatch.setattr(scans, "_resolve_org_id", AsyncMock(return_value=uuid.uuid4()))
    monkeypatch.setattr(
        scans, "_split_by_scan_history", AsyncMock(return_value=([first_id], [rescan_id]))
    )
    monkeypatch.setattr(scans, "get_redis", AsyncMock(return_value=object()))
    monkeypatch.setattr(
        scans,
        "enqueue_rescan_delivery",
        AsyncMock(side_effect=RedisTimeoutError("Timeout reading from localhost:6379")),
    )
    start = AsyncMock(return_value=scan_id)
    monkeypatch.setattr(scans, "start_scan", start)

    resp = await scans.create_scan(
        StartScanRequest(repo_ids=[first_id, rescan_id]),
        current_user=MagicMock(),
        db=MagicMock(),
    )

    # First-scan repo dispatched despite the re-scan enqueue error.
    assert resp.scan_id == scan_id
    assert start.await_args.kwargs["repo_ids"] == [first_id]
    # Re-scan deferred (no delivery), but the request still succeeds and the
    # count reflects what the caller requested.
    assert resp.rescan_delivery_ids == []
    assert resp.rescan_repo_count == 1


async def test_rescan_proceeds_when_redis_up(monkeypatch: pytest.MonkeyPatch) -> None:
    repo_id = uuid.uuid4()
    monkeypatch.setattr(scans, "_resolve_org_id", AsyncMock(return_value=uuid.uuid4()))
    monkeypatch.setattr(scans, "_split_by_scan_history", AsyncMock(return_value=([], [repo_id])))
    monkeypatch.setattr(scans, "get_redis", AsyncMock(return_value=object()))
    monkeypatch.setattr(scans, "enqueue_rescan_delivery", AsyncMock(return_value="rescan-x"))

    resp = await scans.create_scan(
        StartScanRequest(repo_ids=[repo_id]), current_user=MagicMock(), db=MagicMock()
    )

    assert resp.rescan_delivery_ids == ["rescan-x"]


async def test_first_scan_does_not_need_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    """First-time scans use the in-process pipeline, so the Redis guard skips them."""
    repo_id = uuid.uuid4()
    scan_id = uuid.uuid4()
    monkeypatch.setattr(scans, "_resolve_org_id", AsyncMock(return_value=uuid.uuid4()))
    monkeypatch.setattr(scans, "_split_by_scan_history", AsyncMock(return_value=([repo_id], [])))
    monkeypatch.setattr(scans, "start_scan", AsyncMock(return_value=scan_id))
    redis = AsyncMock(return_value=None)
    monkeypatch.setattr(scans, "get_redis", redis)

    resp = await scans.create_scan(
        StartScanRequest(repo_ids=[repo_id]), current_user=MagicMock(), db=MagicMock()
    )

    assert resp.scan_id == scan_id
    redis.assert_not_awaited()  # guard not consulted when there are no re-scans


async def test_multiple_repos_mixed_first_and_rescan_redis_down(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Multi-repo request, Redis down: first-scan + re-scan repos run as ONE direct scan.

    ``start_scan`` may only be called once per org (it raises if a scan is
    already active), so every direct-scan repo — never-scanned plus the
    Redis-fallback re-scans — must go into a single ``start_scan`` call.
    """
    first_a, first_b = uuid.uuid4(), uuid.uuid4()
    rescan_a, rescan_b = uuid.uuid4(), uuid.uuid4()
    scan_id = uuid.uuid4()
    monkeypatch.setattr(scans, "_resolve_org_id", AsyncMock(return_value=uuid.uuid4()))
    monkeypatch.setattr(
        scans,
        "_split_by_scan_history",
        AsyncMock(return_value=([first_a, first_b], [rescan_a, rescan_b])),
    )
    monkeypatch.setattr(scans, "get_redis", AsyncMock(return_value=None))
    enqueue = AsyncMock(return_value="rescan-x")
    monkeypatch.setattr(scans, "enqueue_rescan_delivery", enqueue)
    start = AsyncMock(return_value=scan_id)
    monkeypatch.setattr(scans, "start_scan", start)

    resp = await scans.create_scan(
        StartScanRequest(repo_ids=[first_a, first_b, rescan_a, rescan_b]),
        current_user=MagicMock(),
        db=MagicMock(),
    )

    assert resp.scan_id == scan_id
    assert resp.rescan_delivery_ids == []
    enqueue.assert_not_awaited()
    start.assert_awaited_once()  # exactly one scan for all four repos
    assert start.await_args.kwargs["repo_ids"] == [first_a, first_b, rescan_a, rescan_b]


async def test_multiple_repos_rescan_when_redis_up(monkeypatch: pytest.MonkeyPatch) -> None:
    """Multi-repo, Redis up: first-scans run directly; each re-scan is enqueued."""
    first_a = uuid.uuid4()
    rescan_a, rescan_b = uuid.uuid4(), uuid.uuid4()
    scan_id = uuid.uuid4()
    monkeypatch.setattr(scans, "_resolve_org_id", AsyncMock(return_value=uuid.uuid4()))
    monkeypatch.setattr(
        scans,
        "_split_by_scan_history",
        AsyncMock(return_value=([first_a], [rescan_a, rescan_b])),
    )
    monkeypatch.setattr(scans, "get_redis", AsyncMock(return_value=object()))
    monkeypatch.setattr(
        scans,
        "enqueue_rescan_delivery",
        AsyncMock(side_effect=["rescan-1", "rescan-2"]),
    )
    start = AsyncMock(return_value=scan_id)
    monkeypatch.setattr(scans, "start_scan", start)

    resp = await scans.create_scan(
        StartScanRequest(repo_ids=[first_a, rescan_a, rescan_b]),
        current_user=MagicMock(),
        db=MagicMock(),
    )

    assert resp.scan_id == scan_id  # first-scan repo ran directly
    assert resp.rescan_delivery_ids == ["rescan-1", "rescan-2"]  # both re-scans queued
    assert start.await_args.kwargs["repo_ids"] == [first_a]  # only the never-scanned repo
