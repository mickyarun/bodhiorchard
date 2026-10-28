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

"""Who may deliver to the repository webhook: signatures and secrets.

Every refusal must happen before anything is recorded or handled. The Redis
stream publish is replaced by a recorder; nothing talks to GitHub.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.api.v1 import github_webhook as gh_webhook
from app.api.v1.github_webhook import _verify_github_signature
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


def test_the_verifier_and_the_helper_match_githubs_published_example() -> None:
    """GitHub's documented known-answer vector for X-Hub-Signature-256."""
    secret, body = "It's a Secret to Everybody", b"Hello, World!"
    expected = "sha256=757107ea0eb2509fc211221cce984b8a37570b6d7586c22c46f4379c8b043e17"
    assert _verify_github_signature(secret, body, expected) is True
    assert signed_headers(body, "d", secret=secret)["X-Hub-Signature-256"] == expected
    assert _verify_github_signature(secret, body + b" ", expected) is False


@pytest.mark.parametrize(
    "tamper",
    ["wrong-secret", "tampered-body", "no-prefix"],
)
async def test_a_bad_signature_is_refused_before_anything_is_recorded(
    client: AsyncClient, pg_session_factory: Factory, calls: WebhookCalls, tamper: str
) -> None:
    _, _, full_name = await tracked_repo(pg_session_factory)
    body = merged_pr_payload(full_name)
    delivery = uuid.uuid4().hex
    headers = signed_headers(body, delivery)
    sent = body
    if tamper == "wrong-secret":
        headers = signed_headers(body, delivery, secret="guess")
    elif tamper == "tampered-body":
        sent = body.replace(b'"number": 1', b'"number": 2')
    else:
        headers["X-Hub-Signature-256"] = headers["X-Hub-Signature-256"][len("sha256=") :]

    resp = await client.post(URL, content=sent, headers=headers)

    assert resp.status_code == 401
    assert await delivery_row(pg_session_factory, delivery) is None
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
    assert await delivery_row(pg_session_factory, delivery) is None


async def test_an_org_without_a_webhook_secret_never_processes_deliveries(
    client: AsyncClient, pg_session_factory: Factory, calls: WebhookCalls
) -> None:
    _, _, full_name = await tracked_repo(pg_session_factory, secret=None)
    body = merged_pr_payload(full_name)
    delivery = uuid.uuid4().hex
    resp = await client.post(URL, content=body, headers=signed_headers(body, delivery))
    assert resp.status_code == 200 and resp.text == "No webhook secret configured"
    assert await delivery_row(pg_session_factory, delivery) is None
    assert calls.handled == 0


async def test_each_repo_is_checked_against_its_own_orgs_secret(
    client: AsyncClient, pg_session_factory: Factory, calls: WebhookCalls
) -> None:
    """A secret that is valid for one org's repo does not open another org's repo."""
    _, _, mine = await tracked_repo(pg_session_factory)
    _, _, theirs = await tracked_repo(pg_session_factory, secret="their-secret")
    to_mine, to_theirs = merged_pr_payload(mine), merged_pr_payload(theirs)

    crossed = await client.post(
        URL,
        content=to_mine,
        headers=signed_headers(to_mine, uuid.uuid4().hex, secret="their-secret"),
    )
    own = await client.post(
        URL,
        content=to_theirs,
        headers=signed_headers(to_theirs, uuid.uuid4().hex, secret="their-secret"),
    )

    assert crossed.status_code == 401
    assert own.status_code == 200
    assert calls.handled == 1


async def test_a_stored_secret_that_cannot_be_decrypted_refuses_the_delivery(
    client: AsyncClient,
    pg_session_factory: Factory,
    calls: WebhookCalls,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, _, full_name = await tracked_repo(pg_session_factory)
    monkeypatch.setattr(gh_webhook, "decrypt_secret", lambda stored: "")
    body = merged_pr_payload(full_name)
    delivery = uuid.uuid4().hex

    resp = await client.post(URL, content=body, headers=signed_headers(body, delivery))

    assert resp.status_code == 401
    assert await delivery_row(pg_session_factory, delivery) is None
    assert calls.handled == 0
