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

"""Repository-scoped GitHub deliveries through the real endpoint and database.

Covers the signature gate, the delivery ledger (replay vs audit rows,
duplicate redelivery) and the ``main_branch`` gate that decides whether a
merge is queued for feature reconciliation. The Redis stream publish is
replaced by a recorder; nothing talks to GitHub.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from typing import Any

import pytest
from httpx import AsyncClient

from app.api.v1 import github_webhook as gh_webhook
from app.models.tracked_repository import SetupPrState, TrackedRepository
from app.models.webhook_log import WebhookDeliveryStatus, WebhookLog
from tests.integration.github_webhook_support import (
    SECRET,
    WebhookCalls,
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


async def _log(factory: Factory, delivery: str) -> WebhookLog | None:
    async with factory() as db:
        return await db.get(WebhookLog, delivery)


async def test_a_merge_into_main_is_queued_for_reconciliation(
    client: AsyncClient, pg_session_factory: Factory, calls: WebhookCalls
) -> None:
    org, repo, full_name = await tracked_repo(pg_session_factory, setup_pr_number=7)
    body = merged_pr_payload(full_name, number=7, base="main")
    delivery = uuid.uuid4().hex

    resp = await client.post(URL, content=body, headers=signed_headers(body, delivery))

    assert resp.status_code == 200
    row = await _log(pg_session_factory, delivery)
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
    row = await _log(pg_session_factory, delivery)
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
    row = await _log(pg_session_factory, delivery)
    assert row is not None and row.status == WebhookDeliveryStatus.PENDING


@pytest.mark.parametrize(
    "tamper",
    ["wrong-secret", "tampered-body", "no-prefix", "other-orgs-secret"],
)
async def test_a_bad_signature_is_refused_before_anything_is_recorded(
    client: AsyncClient, pg_session_factory: Factory, calls: WebhookCalls, tamper: str
) -> None:
    _, _, full_name = await tracked_repo(pg_session_factory)
    await tracked_repo(pg_session_factory, secret="the-other-orgs-secret")
    body = merged_pr_payload(full_name)
    delivery = uuid.uuid4().hex
    headers = signed_headers(body, delivery)
    sent = body
    if tamper == "wrong-secret":
        headers = signed_headers(body, delivery, secret="guess")
    elif tamper == "tampered-body":
        sent = body.replace(b'"number": 1', b'"number": 2')
    elif tamper == "no-prefix":
        headers["X-Hub-Signature-256"] = headers["X-Hub-Signature-256"][len("sha256=") :]
    else:
        headers = signed_headers(body, delivery, secret="the-other-orgs-secret")

    resp = await client.post(URL, content=sent, headers=headers)

    assert resp.status_code == 401
    assert await _log(pg_session_factory, delivery) is None
    assert calls.handled == 0 and calls.published == []


@pytest.mark.parametrize(
    ("drop", "status"),
    [("X-Hub-Signature-256", 400), ("X-GitHub-Event", 400), ("X-GitHub-Delivery", 400)],
)
async def test_missing_headers_are_refused(
    client: AsyncClient, pg_session_factory: Factory, calls: WebhookCalls, drop: str, status: int
) -> None:
    _, _, full_name = await tracked_repo(pg_session_factory)
    body = merged_pr_payload(full_name)
    headers = signed_headers(body, uuid.uuid4().hex)
    headers.pop(drop)
    assert (await client.post(URL, content=body, headers=headers)).status_code == status
    assert calls.handled == 0


async def test_invalid_json_is_refused(client: AsyncClient, calls: WebhookCalls) -> None:
    body = b"{not json"
    resp = await client.post(URL, content=body, headers=signed_headers(body, uuid.uuid4().hex))
    assert resp.status_code == 400


async def test_an_untracked_repository_is_acknowledged_and_ignored(
    client: AsyncClient, pg_session_factory: Factory, calls: WebhookCalls
) -> None:
    body = merged_pr_payload(f"nobody/{uuid.uuid4().hex}")
    delivery = uuid.uuid4().hex
    resp = await client.post(URL, content=body, headers=signed_headers(body, delivery))
    assert resp.status_code == 200 and resp.text == "Repository not tracked"
    assert await _log(pg_session_factory, delivery) is None


async def test_an_org_without_a_webhook_secret_never_processes_deliveries(
    client: AsyncClient, pg_session_factory: Factory, calls: WebhookCalls
) -> None:
    _, _, full_name = await tracked_repo(pg_session_factory, secret=None)
    body = merged_pr_payload(full_name)
    delivery = uuid.uuid4().hex
    resp = await client.post(URL, content=body, headers=signed_headers(body, delivery))
    assert resp.status_code == 200 and resp.text == "No webhook secret configured"
    assert await _log(pg_session_factory, delivery) is None
    assert calls.handled == 0


def test_the_helper_signs_exactly_the_bytes_it_sends() -> None:
    """Guard the fixture: the header is the HMAC of the body under the org secret."""
    body = merged_pr_payload("o/r")
    parsed: dict[str, Any] = json.loads(body)
    expected = hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    assert parsed["pull_request"]["merged"] is True
    assert signed_headers(body, "d")["X-Hub-Signature-256"] == f"sha256={expected}"
