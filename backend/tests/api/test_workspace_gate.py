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

"""Every API route is either behind the engineering gate or deliberately shared.

The router split is default-deny. This test makes the "deliberately"
part enforceable: a new router mounted outside the engineering group, or a
new route added to a shared module, fails here until someone decides it
belongs in the shared list. A people-only role (sales) must never reach
engineering data by accident.
"""

from app.api.router import api_router
from app.core.permissions import WORKSPACE_ENGINEERING
from tests.api.route_walk import ServedRoute, depends_on, served_routes

# Modules whose routes are open to any authenticated member, or that
# authenticate with their own credential (webhook signature, MCP token,
# Colyseus bridge secret).
SHARED_MODULES = frozenset(
    {
        "app.api.health",
        "app.api.v1.auth",
        "app.api.v1.employee_documents",
        "app.api.v1.employee_sensitive",
        "app.api.v1.employee_updates",
        "app.api.v1.employees",
        "app.api.v1.leave",
        "app.api.v1.leave_approvals",
        "app.api.v1.leave_balances",
        "app.api.v1.leave_calendar",
        "app.api.v1.leave_digest",
        "app.api.v1.leave_holidays",
        "app.api.v1.leave_policies",
        "app.api.v1.leave_types",
        "app.api.v1.github_webhook",
        "app.api.v1.internal_colyseus",
        "app.api.v1.members",
        "app.api.v1.me",
        "app.api.v1.offices",
        "app.api.v1.notifications",
        "app.api.v1.organizations",
        "app.api.v1.public",
        "app.api.v1.roles",
        "app.api.v1.settings",
        "app.api.v1.setup",
        "app.api.v1.slack",
        "app.api.v1.slack_interactions",
        "app.api.v1.ws",
        "app.mcp.server",
        "app.mcp.streamable",
    }
)

# Modules that mix a gated user-facing router with an ungated bridge
# router. Only the bridge paths may be ungated.
BRIDGE_PATH_PREFIX = "/api/v1/internal/colyseus/"
MIXED_MODULES = frozenset({"app.api.v1.backlash", "app.api.v1.races"})

# Shared-module routes that still carry engineering data.
MUST_BE_GATED = frozenset(
    {
        "/api/v1/me/mcp-token",
        "/api/v1/me/mcp-token/status",
        "/api/v1/me/mcp-tokens",
        "/api/v1/me/mcp-tokens/{token_id}",
        "/api/v1/settings/quiz",
        "/api/v1/settings/mcp-token",
        "/api/v1/settings/mcp-token/status",
    }
)


def _requires_engineering(call: object) -> bool:
    return WORKSPACE_ENGINEERING in getattr(call, "required_permissions", ())


def _is_gated(route: ServedRoute) -> bool:
    """The gate is in the dependencies FastAPI solves for this route."""
    return depends_on(route, _requires_engineering)


def _routes() -> list[ServedRoute]:
    routes = served_routes(api_router)
    # Hundreds today; a walk that finds none would let every check pass.
    assert len(routes) > 200, f"only {len(routes)} routes found"
    return routes


def test_every_route_is_gated_or_shared() -> None:
    offenders = []
    for route in _routes():
        module = route.module
        if _is_gated(route):
            continue
        if module in SHARED_MODULES:
            continue
        if module in MIXED_MODULES and route.path.startswith(BRIDGE_PATH_PREFIX):
            continue
        offenders.append(f"{module}: {route.path}")
    assert offenders == [], "Ungated routes outside the shared list:\n" + "\n".join(offenders)


def test_engineering_data_in_shared_modules_is_gated() -> None:
    found = {r.path for r in _routes() if r.path in MUST_BE_GATED}
    assert found == MUST_BE_GATED, f"missing routes: {MUST_BE_GATED - found}"
    ungated = {r.path for r in _routes() if r.path in MUST_BE_GATED} - {
        r.path for r in _routes() if _is_gated(r)
    }
    assert ungated == set()


def test_engineering_settings_subrouters_are_gated() -> None:
    for route in _routes():
        if route.path.startswith(("/api/v1/settings/repos", "/api/v1/settings/slack")):
            assert _is_gated(route), route.path


def test_core_engineering_routes_are_gated() -> None:
    prefixes = ("/api/v1/buds", "/api/v1/bugs", "/api/v1/dashboard", "/api/v1/features")
    gated = [r for r in _routes() if r.path.startswith(prefixes)]
    assert gated, "expected engineering routes to exist"
    assert all(_is_gated(r) for r in gated)
