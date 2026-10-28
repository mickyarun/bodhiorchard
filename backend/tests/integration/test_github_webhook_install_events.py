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

"""GitHub App installation deliveries through the real endpoint and database.

These carry no repository; the org is found by ``installation.app_id`` and
its own webhook secret must sign the body. Redelivery is applied once.
"""

from __future__ import annotations

import json
import uuid

import pytest
from httpx import AsyncClient, Response

from app.api.v1 import github_webhook as gh_webhook
from app.core.encryption import encrypt_secret
from app.models.organization import Organization
from tests.integration.github_webhook_support import (
    SECRET,
    WebhookCalls,
    delivery_row,
    signed_headers,
)
from tests.integration.scan_features_bugs_support import Factory, new_org

pytestmark = pytest.mark.integration

URL = "/api/v1/webhooks/github"


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch, pg_session_factory: Factory) -> WebhookCalls:
    """Route the endpoint at the test database."""
    return WebhookCalls.install(monkeypatch, gh_webhook, pg_session_factory)


async def _app_org(factory: Factory) -> tuple[uuid.UUID, int]:
    """An org with its own GitHub App id and webhook secret."""
    app_id = 10**6 + uuid.uuid4().int % 10**9
    org = await new_org(
        factory, github_app_id=app_id, github_webhook_secret=encrypt_secret(SECRET)
    )
    return org, app_id


def _install_body(app_id: int, install_id: int, action: str = "created") -> bytes:
    payload = {"action": action, "installation": {"id": install_id, "app_id": app_id}}
    return json.dumps(payload).encode()


async def _install_id(factory: Factory, org: uuid.UUID) -> int | None:
    async with factory() as db:
        row = await db.get(Organization, org)
        assert row is not None
        return row.github_app_installation_id


async def _send(client: AsyncClient, body: bytes, delivery: str, secret: str = SECRET) -> Response:
    headers = signed_headers(body, delivery, secret=secret, event="installation")
    return await client.post(URL, content=body, headers=headers)


async def test_an_install_is_recorded_once_even_when_redelivered(
    client: AsyncClient, pg_session_factory: Factory, calls: WebhookCalls
) -> None:
    org, app_id = await _app_org(pg_session_factory)
    delivery = uuid.uuid4().hex

    first = await _send(client, _install_body(app_id, 111), delivery)
    replay = await _send(client, _install_body(app_id, 222), delivery)

    assert first.status_code == 200
    assert replay.json() == {"status": "duplicate"}
    assert await _install_id(pg_session_factory, org) == 111
    row = await delivery_row(pg_session_factory, delivery)
    assert row is not None and row.org_id == org


async def test_a_badly_signed_install_changes_nothing(
    client: AsyncClient, pg_session_factory: Factory, calls: WebhookCalls
) -> None:
    org, app_id = await _app_org(pg_session_factory)
    delivery = uuid.uuid4().hex

    resp = await _send(client, _install_body(app_id, 333), delivery, secret="guess")

    assert resp.status_code == 401
    assert await _install_id(pg_session_factory, org) is None
    assert await delivery_row(pg_session_factory, delivery) is None


async def test_uninstalling_clears_the_installation(
    client: AsyncClient, pg_session_factory: Factory, calls: WebhookCalls
) -> None:
    org, app_id = await _app_org(pg_session_factory)
    await _send(client, _install_body(app_id, 444), uuid.uuid4().hex)

    await _send(client, _install_body(app_id, 444, action="deleted"), uuid.uuid4().hex)

    assert await _install_id(pg_session_factory, org) is None


async def test_an_unknown_app_is_acknowledged_and_ignored(
    client: AsyncClient, pg_session_factory: Factory, calls: WebhookCalls
) -> None:
    delivery = uuid.uuid4().hex
    resp = await _send(client, _install_body(2_000_000_000, 555), delivery)
    assert resp.status_code == 200 and resp.text == "No matching org"
    assert await delivery_row(pg_session_factory, delivery) is None
