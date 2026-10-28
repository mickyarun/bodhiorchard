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

"""Repository-scoped GitHub deliveries: the delivery ledger and the main-branch gate.

Only a merge into the repo's ``main_branch`` is queued for feature
reconciliation; every other pull_request delivery leaves an audit row.
Redelivery is acknowledged once. The Redis stream publish is replaced by a
recorder; nothing talks to GitHub.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.api.v1 import github_webhook as gh_webhook
from app.models.tracked_repository import SetupPrState, TrackedRepository
from app.models.webhook_log import WebhookDeliveryStatus
from tests.integration.github_webhook_support import (
    WebhookCalls,
    delivery_row,
    merged_pr_payload,
    signed_headers,
    tracked_repo,
)
from tests.integration.scan_features_bugs_support import Factory

pytestmark = pytest.mark.integration

URL = "/api/v1/webhooks/github"


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch, pg_session_factory: Factory) -> WebhookCalls:
    """Route the endpoint at the test database and record handler + publish calls."""
    return WebhookCalls.install(monkeypatch, gh_webhook, pg_session_factory)


async def test_a_merge_into_main_is_queued_for_reconciliation(
    client: AsyncClient, pg_session_factory: Factory, calls: WebhookCalls
) -> None:
    org, repo, full_name = await tracked_repo(pg_session_factory, setup_pr_number=7)
    body = merged_pr_payload(full_name, number=7, base="main")
    delivery = uuid.uuid4().hex

    resp = await client.post(URL, content=body, headers=signed_headers(body, delivery))

    assert resp.status_code == 200
    row = await delivery_row(pg_session_factory, delivery)
    assert row is not None and row.status == WebhookDeliveryStatus.PENDING
    assert row.org_id == org and row.repo_id == repo
    assert row.payload == {
        "action": "closed", "merged": True, "pr_number": 7, "full_name": full_name,
        "base_sha": "b" * 40, "head_sha": "m" * 40,
    }  # fmt: skip
    assert calls.published == [(org, repo, delivery)]
    async with pg_session_factory() as db:
        stored = await db.get(TrackedRepository, repo)
        assert stored is not None and stored.setup_pr_state == SetupPrState.MERGED


@pytest.mark.parametrize(
    ("main_branch", "base"),
    [("main", "develop"), ("main", "release/uat"), (None, "main")],
    ids=["develop", "release-branch", "no-main-configured"],
)
async def test_merges_off_the_main_branch_are_logged_but_never_queued(
    client: AsyncClient,
    pg_session_factory: Factory,
    calls: WebhookCalls,
    main_branch: str | None,
    base: str,
) -> None:
    _, _, full_name = await tracked_repo(pg_session_factory, main_branch=main_branch)
    body = merged_pr_payload(full_name, base=base)
    delivery = uuid.uuid4().hex

    resp = await client.post(URL, content=body, headers=signed_headers(body, delivery))

    assert resp.status_code == 200
    row = await delivery_row(pg_session_factory, delivery)
    assert row is not None and row.status == WebhookDeliveryStatus.SKIPPED
    assert row.payload is None
    assert calls.published == []
    assert calls.handled == 1


async def test_a_redelivered_merge_is_acknowledged_once(
    client: AsyncClient, pg_session_factory: Factory, calls: WebhookCalls
) -> None:
    _, _, full_name = await tracked_repo(pg_session_factory)
    body = merged_pr_payload(full_name)
    delivery = uuid.uuid4().hex

    first = await client.post(URL, content=body, headers=signed_headers(body, delivery))
    second = await client.post(URL, content=body, headers=signed_headers(body, delivery))

    assert first.status_code == 200 and first.text == "OK"
    assert second.status_code == 200 and second.json() == {"status": "duplicate"}
    assert calls.handled == 1
    assert len(calls.published) == 1


async def test_a_publish_failure_still_acknowledges_and_keeps_the_row_pending(
    client: AsyncClient, pg_session_factory: Factory, calls: WebhookCalls
) -> None:
    _, _, full_name = await tracked_repo(pg_session_factory)
    calls.publish_error = ConnectionError("redis down")
    body = merged_pr_payload(full_name)
    delivery = uuid.uuid4().hex

    resp = await client.post(URL, content=body, headers=signed_headers(body, delivery))

    assert resp.status_code == 200
    row = await delivery_row(pg_session_factory, delivery)
    assert row is not None and row.status == WebhookDeliveryStatus.PENDING


@pytest.mark.parametrize(
    ("action", "merged"),
    [("closed", False), ("opened", False), ("synchronize", False)],
    ids=["closed-unmerged", "opened", "synchronize"],
)
async def test_pull_requests_that_are_not_merges_are_logged_but_never_queued(
    client: AsyncClient,
    pg_session_factory: Factory,
    calls: WebhookCalls,
    action: str,
    merged: bool,
) -> None:
    _, _, full_name = await tracked_repo(pg_session_factory)
    body = merged_pr_payload(full_name, base="main", action=action, merged=merged)
    delivery = uuid.uuid4().hex

    resp = await client.post(URL, content=body, headers=signed_headers(body, delivery))

    assert resp.status_code == 200
    row = await delivery_row(pg_session_factory, delivery)
    assert row is not None and row.status == WebhookDeliveryStatus.SKIPPED
    assert row.payload is None
    assert calls.published == [] and calls.handled == 1
