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

"""The AI credential and the GitHub App key, saved and read on Postgres.

Neither is ever returned: the AI settings report ``has_api_key`` and the
GitHub settings ``hasPrivateKey``. The process-env push and the GitHub
App validation call are replaced by recorders, so nothing leaves the test.
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient

from app.api.v1 import settings as settings_api
from app.api.v1 import settings_claude
from tests.integration.settings_support import (
    Factory,
    assert_ciphertext_of,
    load_org,
    make_org,
)

pytestmark = pytest.mark.integration

CLAUDE = "/api/v1/settings/claude"
CONNECTIONS = "/api/v1/settings/connections"
KEY = "sk-ant-api03-plaintext-key-0000"
PEM = "-----BEGIN RSA PRIVATE KEY-----\nplaintextkeymaterial\n-----END RSA PRIVATE KEY-----"


@pytest.fixture(autouse=True)
def no_side_effects(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []
    monkeypatch.setattr(settings_claude, "apply_claude_auth_to_env", lambda _org: None)

    async def _validate(org: Any, _db: Any) -> None:
        calls.append("validate")
        org.github_app_slug = "acme-bot"

    monkeypatch.setattr(settings_api, "validate_and_persist_app_slug", _validate)
    return calls


async def test_an_api_key_is_stored_encrypted_and_never_returned(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org = await make_org(pg_session_factory)
    saved = await client.patch(
        CLAUDE, headers=org.owner.headers, json={"auth_mode": "api_key", "api_key": f" {KEY} "}
    )
    read = await client.get(CLAUDE, headers=org.developer.headers)

    assert saved.status_code == read.status_code == 200, saved.text
    assert KEY not in saved.text and KEY not in read.text
    assert read.json()["has_api_key"] is True
    stored = await load_org(pg_session_factory, org.id)
    assert_ciphertext_of(stored.claude_api_key_encrypted, KEY)


async def test_switching_mode_needs_a_new_credential_and_host_clears_it(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org = await make_org(pg_session_factory)
    headers = org.owner.headers
    await client.patch(CLAUDE, headers=headers, json={"auth_mode": "api_key", "api_key": KEY})

    switched = await client.patch(CLAUDE, headers=headers, json={"auth_mode": "subscription"})
    assert switched.status_code == 400
    assert "oauth_token is required" in switched.json()["detail"]
    kept = await load_org(pg_session_factory, org.id)
    assert kept.claude_auth_mode == "api_key"
    assert_ciphertext_of(kept.claude_api_key_encrypted, KEY)

    same_mode = await client.patch(CLAUDE, headers=headers, json={"auth_mode": "api_key"})
    assert same_mode.json()["has_api_key"] is True

    host = await client.patch(CLAUDE, headers=headers, json={"auth_mode": "host"})
    assert host.json()["has_api_key"] is False
    assert (await load_org(pg_session_factory, org.id)).claude_api_key_encrypted is None


@pytest.mark.parametrize(
    ("body", "detail"),
    [
        ({"auth_mode": "api_key", "api_key": "   "}, "cannot be blank"),
        ({"auth_mode": "carrier-pigeon"}, "auth_mode must be one of"),
        ({"provider": "skynet", "auth_mode": "host"}, "provider must be one of"),
    ],
)
async def test_bad_updates_are_400_and_change_nothing(
    client: AsyncClient, pg_session_factory: Factory, body: dict[str, str], detail: str
) -> None:
    org = await make_org(pg_session_factory)
    before = await load_org(pg_session_factory, org.id)
    response = await client.patch(CLAUDE, headers=org.owner.headers, json=body)
    assert response.status_code == 400
    assert detail in response.json()["detail"]
    after = await load_org(pg_session_factory, org.id)
    assert (after.claude_auth_mode, after.claude_api_key_encrypted) == (
        before.claude_auth_mode,
        before.claude_api_key_encrypted,
    )


async def test_a_developer_cannot_change_the_ai_credential(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org = await make_org(pg_session_factory)
    response = await client.patch(
        CLAUDE, headers=org.developer.headers, json={"auth_mode": "api_key", "api_key": KEY}
    )
    assert response.status_code == 403
    assert (await load_org(pg_session_factory, org.id)).claude_api_key_encrypted is None


async def test_the_github_app_key_is_encrypted_and_only_its_presence_is_read(
    client: AsyncClient, pg_session_factory: Factory, no_side_effects: list[str]
) -> None:
    org = await make_org(pg_session_factory)
    body = {"github": {"appId": 4242, "privateKey": PEM, "webhookSecret": "whsec-plain"}}

    saved = await client.patch(CONNECTIONS, headers=org.owner.headers, json=body)
    read = await client.get(CONNECTIONS, headers=org.owner.headers)

    assert saved.status_code == read.status_code == 200, saved.text
    for response in (saved, read):
        assert "plaintextkeymaterial" not in response.text
        assert "whsec-plain" not in response.text
        assert "BEGIN RSA PRIVATE KEY" not in response.text
    github = saved.json()["github"]
    assert (github["hasPrivateKey"], github["webhookConfigured"]) == (True, True)
    assert github["status"] == "awaiting_install"
    assert no_side_effects == ["validate"]
    stored = await load_org(pg_session_factory, org.id)
    assert_ciphertext_of(stored.github_app_private_key, PEM)
    assert_ciphertext_of(stored.github_webhook_secret, "whsec-plain")
