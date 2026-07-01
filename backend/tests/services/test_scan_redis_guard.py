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

"""Guard: ``create_scan`` refuses re-scans loudly when Redis is unreachable.

Re-scans are consumed by the PR-merge Redis-stream worker, which only starts
at boot when Redis is up. Without this guard a re-scan enqueues but never runs,
surfacing as a silent 202 with no progress (the exact failure this prevents).
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.api.v1 import scans
from app.schemas.scan import StartScanRequest


async def test_rescan_returns_503_when_redis_down(monkeypatch: pytest.MonkeyPatch) -> None:
    repo_id = uuid.uuid4()
    monkeypatch.setattr(scans, "_resolve_org_id", AsyncMock(return_value=uuid.uuid4()))
    monkeypatch.setattr(scans, "_split_by_scan_history", AsyncMock(return_value=([], [repo_id])))
    monkeypatch.setattr(scans, "get_redis", AsyncMock(return_value=None))
    enqueue = AsyncMock(return_value="rescan-x")
    monkeypatch.setattr(scans, "enqueue_rescan_delivery", enqueue)

    with pytest.raises(HTTPException) as exc:
        await scans.create_scan(
            StartScanRequest(repo_ids=[repo_id]), current_user=MagicMock(), db=MagicMock()
        )

    assert exc.value.status_code == 503
    assert "Redis" in str(exc.value.detail)
    enqueue.assert_not_awaited()  # never enqueued a delivery that would sit pending


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
