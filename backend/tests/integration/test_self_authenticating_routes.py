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

"""Routes that skip the user token still refuse a caller without their own credential.

The route-walk unit test pins which routes these are; this calls each one
for real (against Postgres, since the MCP token and Slack checks read it)
with a wrong or missing credential.
"""

from __future__ import annotations

import json
import uuid
from urllib.parse import urlencode

import pytest
from httpx import AsyncClient

from app.api.router import api_router
from app.core.security import create_access_token
from tests.api.route_walk import served_routes
from tests.integration.auth_tenancy_support import new_tenant
from tests.integration.leave_support import Factory

pytestmark = pytest.mark.integration
BRIDGE = "/api/v1/internal/colyseus/"


def _calls(prefix: str) -> list[tuple[str, str]]:
    calls = []
    for route in served_routes(api_router):
        if not route.path.startswith(prefix) or route.path == "/mcp/tools":
            continue
        path = route.path.replace("{org_id}", str(uuid.uuid4())).replace("{tool_name}", "x")
        calls.extend((method, path) for method in sorted(route.methods - {"HEAD"}))
    assert calls, prefix
    return calls


async def test_the_game_server_bridge_needs_the_shared_secret(client: AsyncClient) -> None:
    for headers in ({}, {"X-Bridge-Secret": "guessed-secret"}):
        for method, path in _calls(BRIDGE):
            response = await client.request(method, path, json={}, headers=headers)
            assert response.status_code == 401, (method, path, headers)


async def test_mcp_routes_refuse_anything_but_an_mcp_token(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    t = await new_tenant(pg_session_factory)
    user_jwt = create_access_token({"sub": str(t.owner), "org_id": str(t.org)})
    for method, path in _calls("/mcp/"):
        # No Authorization header at all fails header validation.
        missing = await client.request(method, path, json={})
        assert missing.status_code == 422, (method, path)
        for token in ("bodhi_not-a-real-token", user_jwt):
            headers = {"Authorization": f"Bearer {token}"}
            response = await client.request(method, path, json={}, headers=headers)
            assert response.status_code == 401, (method, path, token)


async def test_slack_and_github_refuse_unsigned_requests(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    event = {"type": "event_callback", "team_id": "T-UNKNOWN", "event": {"type": "message"}}
    unsigned_event = await client.post("/api/v1/slack/events", content=json.dumps(event))
    assert unsigned_event.status_code == 401
    # A signed-looking event is checked through the app's own engine, not the
    # test database, so only the unsigned case runs here.

    action = {"type": "block_actions", "team": {"id": "T-UNKNOWN"}, "actions": []}
    form = urlencode({"payload": json.dumps(action)})
    interaction = await client.post(
        "/api/v1/slack/interactions",
        content=form,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert interaction.status_code == 401

    github = await client.post(
        "/api/v1/webhooks/github",
        content=b"{}",
        headers={"X-GitHub-Event": "push", "X-GitHub-Delivery": str(uuid.uuid4())},
    )
    assert github.status_code == 400
