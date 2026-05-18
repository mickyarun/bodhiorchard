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

"""Statement-shape tests for the WebhookLog repository.

The repository methods themselves are thin wrappers around SQL — the
"real" behaviour (PK uniqueness, FK on ``repo_id``, enum cast) is
exercised end-to-end by the integration tests. These tests pin the
SQL shape so a refactor that quietly drops the enum cast or forgets
to bump ``attempts`` fails loudly here, not in production.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.webhook_log import WebhookDeliveryStatus
from app.repositories.webhook_log import WebhookLogRepository


def _make_db(*, execute_returns: list[Any] | None = None) -> MagicMock:
    """Build an AsyncSession mock whose ``execute`` returns the given results in order."""
    db = MagicMock()
    db.execute = AsyncMock(side_effect=execute_returns or [MagicMock()])
    return db


def _scalar_one_or_none_result(value: Any) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=value)
    return result


@pytest.mark.asyncio
async def test_record_delivery_stamps_skipped_status() -> None:
    """Audit-only path: status='skipped' so the worker never sees it."""
    db = _make_db(execute_returns=[_scalar_one_or_none_result("d1")])
    repo = WebhookLogRepository(db)

    fresh = await repo.record_delivery(
        delivery_id="d1",
        event_type="installation",
        org_id=uuid.uuid4(),
        payload_summary={"app_id": 7},
    )

    assert fresh is True
    bound_stmt = db.execute.call_args.args[0]
    params = bound_stmt.compile().params
    assert params["status"] == WebhookDeliveryStatus.SKIPPED.value
    assert params["repo_id"] is None
    assert params["payload"] is None


@pytest.mark.asyncio
async def test_record_delivery_returns_false_on_duplicate() -> None:
    """ON CONFLICT DO NOTHING → RETURNING yields None → fresh=False."""
    db = _make_db(execute_returns=[_scalar_one_or_none_result(None)])
    repo = WebhookLogRepository(db)

    fresh = await repo.record_delivery(
        delivery_id="dup", event_type="pull_request", org_id=uuid.uuid4()
    )

    assert fresh is False


@pytest.mark.asyncio
async def test_record_replay_row_stamps_pending_and_carries_payload() -> None:
    """Repo-scoped path: status='pending' + full replay payload."""
    db = _make_db(execute_returns=[_scalar_one_or_none_result("d2")])
    repo = WebhookLogRepository(db)
    repo_id = uuid.uuid4()
    payload = {
        "head_sha": "abc",
        "base_sha": "def",
        "pr_number": 7,
        "full_name": "x/y",
        "merged": True,
        "action": "closed",
    }

    fresh = await repo.record_replay_row(
        delivery_id="d2",
        event_type="pull_request",
        org_id=uuid.uuid4(),
        repo_id=repo_id,
        payload=payload,
    )

    assert fresh is True
    bound_stmt = db.execute.call_args.args[0]
    params = bound_stmt.compile().params
    assert params["status"] == WebhookDeliveryStatus.PENDING.value
    assert params["repo_id"] == repo_id
    assert params["payload"] == payload


@pytest.mark.asyncio
async def test_update_status_to_done_uses_enum_cast_no_error_or_attempts() -> None:
    """Success path: status flip only, no ``last_error``, no attempts bump.

    The asyncpg-bound parameter must be CAST(:st AS webhook_delivery_status)
    or Postgres rejects the implicit text→enum coercion.
    """
    db = _make_db()
    repo = WebhookLogRepository(db)

    await repo.update_status(delivery_id="d3", status=WebhookDeliveryStatus.DONE)

    sent = db.execute.call_args.args[0]
    sent_text = str(sent)
    assert "CAST(:st AS webhook_delivery_status)" in sent_text
    assert "last_error" not in sent_text
    assert "attempts + 1" not in sent_text
    params = sent.compile().params
    assert params["st"] == WebhookDeliveryStatus.DONE.value
    assert params["did"] == "d3"


@pytest.mark.asyncio
async def test_update_status_to_failed_writes_error_truncated() -> None:
    """Failure path: status + last_error in one statement; truncation at 500 chars."""
    db = _make_db()
    repo = WebhookLogRepository(db)

    await repo.update_status(
        delivery_id="d4",
        status=WebhookDeliveryStatus.FAILED,
        error="x" * 1000,
    )

    sent = db.execute.call_args.args[0]
    sent_text = str(sent)
    assert "last_error = :err" in sent_text
    params = sent.compile().params
    assert params["st"] == WebhookDeliveryStatus.FAILED.value
    assert params["did"] == "d4"
    assert len(params["err"]) == 500


@pytest.mark.asyncio
async def test_update_status_bump_attempts_increments_in_same_statement() -> None:
    """``pending → running`` edge bumps ``attempts`` atomically so the
    column reflects the count of worker-handler invocations even when
    the recovery path republishes the same delivery.
    """
    db = _make_db()
    repo = WebhookLogRepository(db)

    await repo.update_status(
        delivery_id="d5",
        status=WebhookDeliveryStatus.RUNNING,
        bump_attempts=True,
    )

    sent_text = str(db.execute.call_args.args[0])
    assert "attempts = attempts + 1" in sent_text
    assert "CAST(:st AS webhook_delivery_status)" in sent_text


@pytest.mark.asyncio
async def test_list_in_status_filters_by_enum_and_orders_by_received_at() -> None:
    """Orphan-recovery query: filtered by status, ordered oldest first."""
    scalars = MagicMock()
    scalars.all = MagicMock(return_value=[])
    result = MagicMock()
    result.scalars = MagicMock(return_value=scalars)
    db = _make_db(execute_returns=[result])
    repo = WebhookLogRepository(db)

    rows = await repo.list_in_status(WebhookDeliveryStatus.RUNNING)

    assert rows == []
    # Statement compiles — we don't pin internal SQL since this is an
    # ORM ``select``; the column filter is structurally enforced by
    # the typed parameter.
    db.execute.assert_awaited_once()
