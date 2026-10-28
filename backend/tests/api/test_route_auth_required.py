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

"""Every API route needs a signed-in user unless it is deliberately public.

The workspace-gate test decides *which* signed-in members reach a route;
this one makes sure a caller with no valid access token reaches none of
them. Each route is called for real with no token, a token signed with the
wrong key and a refresh token, and must answer 401 before any database
work. The public list is pinned exactly: a new route that skips
``get_current_user`` fails here until someone adds it on purpose.
"""

import re
import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from httpx import ASGITransport, AsyncClient
from jose import jwt

from app.api.router import api_router
from app.config import settings
from app.core.auth_deps import oauth2_scheme
from app.core.deps import get_db
from app.core.security import create_refresh_token
from app.database import get_db as database_get_db
from tests.api.route_walk import ServedRoute, depends_on, served_routes

# Reachable without a user's access token. Most authenticate some other way;
# those are pinned to their checker in ``OWN_CREDENTIAL`` below.
PUBLIC_ROUTES = frozenset(
    {
        "/health/",
        # The first-run wizard runs before any user exists.
        "/api/setup/status",
        "/api/setup/deployment-info",
        "/api/setup/ai-capabilities",
        "/api/setup/check-claude",
        "/api/setup/check-ai",
        "/api/setup/init-org",
        "/api/setup/initialize",
        "/api/v1/auth/login",
        "/api/v1/auth/refresh",
        # Authenticates with ``?token=`` inside the handler.
        "/api/v1/ws",
        # Pre-commit hook; rate-limited, answers only "exists or not".
        "/api/v1/public/{org_id}/bud-check/{bud_number}",
        # ``<img>`` tags and Slack's unfurler send no Authorization header.
        "/api/v1/employees/avatars/{key}",
        # Signed by Slack / GitHub, checked in the handler.
        "/api/v1/slack/events",
        "/api/v1/slack/interactions",
        "/api/v1/slack/status/callback",
        "/api/v1/webhooks/github",
        # Tool catalogue only; calling a tool needs an MCP token.
        "/mcp/tools",
        "/mcp/tools/{tool_name}",
        "/mcp/dev-activity",
        "/mcp/agent-activity",
        "/mcp/sse",
        "/api/v1/internal/colyseus/org-snapshot/{org_id}",
        "/api/v1/internal/colyseus/verify-token",
        "/api/v1/internal/colyseus/race-invite",
        "/api/v1/internal/colyseus/minigame-results",
        "/api/v1/internal/colyseus/backlash-invite",
        "/api/v1/internal/colyseus/backlash-results",
        "/api/v1/internal/colyseus/race-results",
    }
)

# Public routes that must still check their own credential.
OWN_CREDENTIAL = {
    "/mcp/": "verify_mcp_token",
    "/api/v1/internal/colyseus/": "_verify_bridge_secret",
}
MCP_CATALOGUE = "/mcp/tools"


def _needs_user_token(route: ServedRoute) -> bool:
    return depends_on(route, lambda call: call is oauth2_scheme)


def _call_name(call: Any) -> str:
    return str(getattr(call, "__name__", ""))


def test_only_the_pinned_routes_skip_the_user_token() -> None:
    routes = served_routes(api_router)
    assert len(routes) > 300, f"only {len(routes)} routes found"
    public = {r.path for r in routes if not _needs_user_token(r)}
    assert public == PUBLIC_ROUTES


@pytest.mark.parametrize(("prefix", "checker"), sorted(OWN_CREDENTIAL.items()))
def test_self_authenticating_routes_check_their_credential(prefix: str, checker: str) -> None:
    routes = [
        r
        for r in served_routes(api_router)
        if r.path.startswith(prefix) and r.path != MCP_CATALOGUE
    ]
    assert routes, f"no routes under {prefix}"
    unchecked = [
        r.path for r in routes if not depends_on(r, lambda call: _call_name(call) == checker)
    ]
    assert unchecked == []


async def _inert_db() -> AsyncIterator[object]:
    """A stand-in session: any query before the auth check would fail loudly."""
    yield object()


def _bad_tokens() -> dict[str, dict[str, str]]:
    claims = {"sub": str(uuid.uuid4()), "org_id": str(uuid.uuid4())}
    forged = jwt.encode(
        {**claims, "type": "access", "exp": 4_102_444_800},
        "not-the-server-secret",
        algorithm=settings.auth.algorithm,
    )
    return {
        "no token": {},
        "forged signature": {"Authorization": f"Bearer {forged}"},
        "refresh token": {"Authorization": f"Bearer {create_refresh_token(claims)}"},
    }


def _protected_calls(app: FastAPI) -> list[tuple[str, str]]:
    calls = []
    for route in app.routes:
        if not isinstance(route, APIRoute) or route.path in PUBLIC_ROUTES:
            continue
        concrete = re.sub(r"\{[^}]+\}", str(uuid.uuid4()), route.path)
        calls.extend((method, concrete) for method in sorted(route.methods - {"HEAD"}))
    return calls


async def test_every_protected_route_rejects_callers_without_a_valid_access_token() -> None:
    app = FastAPI()
    app.include_router(api_router)
    app.dependency_overrides[get_db] = _inert_db
    app.dependency_overrides[database_get_db] = _inert_db
    calls = _protected_calls(app)
    assert len(calls) > 300, f"only {len(calls)} protected calls found"

    let_through = []
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for label, headers in _bad_tokens().items():
            for method, path in calls:
                response = await client.request(method, path, headers=headers)
                if response.status_code != 401:
                    let_through.append(f"{label}: {method} {path} -> {response.status_code}")
    assert let_through == []
