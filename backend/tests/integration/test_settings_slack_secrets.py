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

"""Slack credentials through ``/settings/connections`` on Postgres.

Both secrets are stored encrypted, read back masked, and a masked value
sent back unchanged (what the form does on an unrelated save) never
overwrites them. Slack itself is replaced by a recorder of ``auth.test``.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.api.v1 import settings as settings_api
from app.core.encryption import decrypt_secret
from tests.integration.settings_support import Factory, load_org, make_org

pytestmark = pytest.mark.integration

URL = "/api/v1/settings/connections"
BOT = "xoxb-1111-2222-plaintextbottoken"
SIGNING = "0123456789abcdef0123456789abcdef"


@pytest.fixture
def slack_teams(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Bot token -> team id that ``auth.test`` reports; records nothing else."""
    teams: dict[str, str] = {}

    async def _auth_test(token: str) -> dict[str, str] | None:
        team = teams.get(token)
        return {"team_id": team} if team else None

    monkeypatch.setattr(settings_api, "auth_test", _auth_test)
    return teams


def _slack(**fields: object) -> dict[str, object]:
    return {"slack": {"enabled": True, **fields}}


async def test_secrets_are_encrypted_at_rest_and_masked_on_read(
    client: AsyncClient, pg_session_factory: Factory, slack_teams: dict[str, str]
) -> None:
    org = await make_org(pg_session_factory)
    slack_teams[BOT] = f"T{uuid.uuid4().hex[:8]}"

    saved = await client.patch(
        URL, headers=org.owner.headers, json=_slack(botToken=BOT, signingSecret=SIGNING)
    )
    read = await client.get(URL, headers=org.owner.headers)

    assert saved.status_code == read.status_code == 200, saved.text
    for response in (saved, read):
        assert BOT not in response.text and SIGNING not in response.text
    slack = read.json()["slack"]
    assert slack["botToken"] == "xoxb****oken"
    assert slack["signingSecret"] == "0123****cdef"
    assert slack["connected"] is True
    assert slack["teamId"] == slack_teams[BOT]

    stored = await load_org(pg_session_factory, org.id)
    assert BOT not in (stored.slack_bot_token or "")
    assert decrypt_secret(stored.slack_bot_token or "") == BOT
    assert decrypt_secret(stored.slack_signing_secret or "") == SIGNING


async def test_sending_the_masked_values_back_keeps_the_real_ones(
    client: AsyncClient, pg_session_factory: Factory, slack_teams: dict[str, str]
) -> None:
    org = await make_org(pg_session_factory)
    slack_teams[BOT] = f"T{uuid.uuid4().hex[:8]}"
    await client.patch(
        URL, headers=org.owner.headers, json=_slack(botToken=BOT, signingSecret=SIGNING)
    )
    masked = (await client.get(URL, headers=org.owner.headers)).json()["slack"]

    response = await client.patch(
        URL,
        headers=org.owner.headers,
        json=_slack(
            botToken=masked["botToken"],
            signingSecret=masked["signingSecret"],
            teamId=masked["teamId"],
        ),
    )

    assert response.status_code == 200, response.text
    stored = await load_org(pg_session_factory, org.id)
    assert decrypt_secret(stored.slack_bot_token or "") == BOT
    assert decrypt_secret(stored.slack_signing_secret or "") == SIGNING


@pytest.mark.parametrize("secret", ["not-hex-at-all-but-long-enough-00", "abcdef", ""])
async def test_a_malformed_signing_secret_is_a_400_and_rolls_back_the_bot_token(
    client: AsyncClient, pg_session_factory: Factory, slack_teams: dict[str, str], secret: str
) -> None:
    org = await make_org(pg_session_factory)
    body = _slack(botToken=BOT, signingSecret=secret or "   ")
    response = await client.patch(URL, headers=org.owner.headers, json=body)

    assert response.status_code == 400
    assert "hex string" in response.json()["detail"]
    stored = await load_org(pg_session_factory, org.id)
    assert stored.slack_bot_token is None
    assert stored.slack_signing_secret is None


async def test_a_workspace_already_connected_elsewhere_is_a_409(
    client: AsyncClient, pg_session_factory: Factory, slack_teams: dict[str, str]
) -> None:
    first, second = await make_org(pg_session_factory), await make_org(pg_session_factory)
    team = f"T{uuid.uuid4().hex[:8]}"
    slack_teams[BOT] = team
    slack_teams["xoxb-second-org-token-0000"] = team
    ok = await client.patch(URL, headers=first.owner.headers, json=_slack(botToken=BOT))
    assert ok.status_code == 200

    taken = await client.patch(
        URL, headers=second.owner.headers, json=_slack(botToken="xoxb-second-org-token-0000")
    )

    assert taken.status_code == 409
    stored = await load_org(pg_session_factory, second.id)
    assert (stored.slack_bot_token, stored.slack_team_id) == (None, None)


async def test_a_developer_can_neither_read_nor_change_connections(
    client: AsyncClient, pg_session_factory: Factory, slack_teams: dict[str, str]
) -> None:
    org = await make_org(pg_session_factory)
    read = await client.get(URL, headers=org.developer.headers)
    write = await client.patch(URL, headers=org.developer.headers, json=_slack(botToken=BOT))
    assert (read.status_code, write.status_code) == (403, 403)
    assert (await load_org(pg_session_factory, org.id)).slack_bot_token is None
