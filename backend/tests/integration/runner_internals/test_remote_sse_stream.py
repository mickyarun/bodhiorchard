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

"""``GET /mcp/sse``: heartbeats, and the stream closing when its token stops being good.

Tokens are minted, revoked and their owners deactivated through the real
HTTP routes; the heartbeat interval is shrunk so a test takes a fraction
of a second.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient

from app.models.user import User
from app.models.user_mcp_token import UserMCPToken
from tests.fakes.seed import Factory, auth_headers, seed_member, seed_org
from tests.integration.runner_internals.sse_support import (
    PING,
    TokenChecks,
    closed_body,
    mint_token,
    open_stream,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def checks(monkeypatch: pytest.MonkeyPatch, app_sessions: Factory) -> TokenChecks:
    """Count the stream's token checks; heartbeat every 10 ms."""
    counter = TokenChecks()
    counter.install(monkeypatch)
    return counter


async def test_revoked_token_closes_the_stream_at_the_next_heartbeat(
    client: AsyncClient, app_sessions: Factory, checks: TokenChecks
) -> None:
    """Heartbeats flow while the token lives; revoking it over HTTP ends the stream."""
    org = await seed_org(app_sessions)
    headers = auth_headers(org.owner_id, org.org_id)
    token, token_id = await mint_token(client, headers)

    stream = open_stream(client, token)
    await checks.reach(3)
    revoked = await client.delete(f"/api/v1/me/mcp-tokens/{token_id}", headers=headers)
    body = await closed_body(stream)

    assert revoked.status_code == 204
    assert body.startswith(": stream ") and body.split("\n", 1)[0].endswith(" ready")
    assert body.count(PING) >= 3
    assert body.count(PING) == checks.count - 1


async def test_token_expiring_mid_stream_closes_it(
    client: AsyncClient, app_sessions: Factory, checks: TokenChecks
) -> None:
    """An ``expires_at`` that passes while connected is caught on the next beat."""
    org = await seed_org(app_sessions)
    token, token_id = await mint_token(client, auth_headers(org.owner_id, org.org_id))

    stream = open_stream(client, token)
    await checks.reach(1)
    async with app_sessions() as db:
        row = await db.get(UserMCPToken, token_id)
        assert row is not None
        row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await db.commit()
    body = await closed_body(stream)

    assert body.count(PING) == checks.count - 1


async def test_deactivating_the_member_over_http_closes_their_stream(
    client: AsyncClient, app_sessions: Factory, checks: TokenChecks
) -> None:
    """Member deactivation revokes the member's tokens, which ends the open stream."""
    org = await seed_org(app_sessions)
    member = await seed_member(app_sessions, org.org_id, "dev")
    token, _ = await mint_token(client, auth_headers(member, org.org_id))

    stream = open_stream(client, token)
    await checks.reach(2)
    toggled = await client.patch(
        f"/api/v1/members/{member}/status", headers=auth_headers(org.owner_id, org.org_id)
    )
    body = await closed_body(stream)

    assert toggled.status_code == 200, toggled.text
    assert body.count(PING) == checks.count - 1
    rejoin = await client.get("/mcp/sse", headers={"Authorization": f"Bearer {token}"})
    assert rejoin.status_code == 401


@pytest.mark.xfail(
    strict=True,
    reason=(
        "the heartbeat re-checks only the token row, not the owner's account, so a "
        "deactivated owner whose token survived keeps the stream; fixed by branch "
        "fix/sse-heartbeat-rechecks-owner"
    ),
)
async def test_owner_deactivated_without_revocation_loses_the_stream(
    client: AsyncClient, app_sessions: Factory, checks: TokenChecks
) -> None:
    """The defence-in-depth case ``verify_mcp_token`` covers for every other call."""
    org = await seed_org(app_sessions)
    member = await seed_member(app_sessions, org.org_id, "dev")
    token, token_id = await mint_token(client, auth_headers(member, org.org_id))

    stream = open_stream(client, token)
    await checks.reach(1)
    async with app_sessions() as db:
        user = await db.get(User, member)
        assert user is not None
        user.is_active = False
        await db.commit()
    done, _ = await asyncio.wait({stream}, timeout=0.5)
    closed_by_itself = bool(done)
    if not done:
        # Still open: end it by removing the token so the test can finish.
        async with app_sessions() as db:
            row = await db.get(UserMCPToken, token_id)
            assert row is not None
            await db.delete(row)
            await db.commit()
    body = await closed_body(stream)

    assert closed_by_itself
    assert body.count(PING) == checks.count - 1
