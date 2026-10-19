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

"""AI-provider capabilities endpoint.

Serves the per-provider capability table (models, effort, auth modes, install
hints) plus the org's current provider and the deployment mode, so the setup
wizard and Agent Prompts UI can build provider-aware, deployment-gated
controls from a single source of truth.
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db, require_permissions
from app.models.organization import AIProvider, Organization
from app.models.user import User
from app.repositories.organization import OrganizationRepository
from app.services.agent_phase_support import provider_limitations
from app.services.ai_runner.capabilities import CAPABILITIES, capabilities_for
from app.services.ai_runner.capability_gate import org_api_key
from app.services.ai_runner.ollama_models import (
    OLLAMA_DEFAULT_BASE_URL,
    clean_base_url,
    list_tool_models,
)
from app.services.deployment_info import deployment_info

router = APIRouter(tags=["settings-ai"])


def serialize_provider(provider: AIProvider) -> dict[str, Any]:
    """JSON-able view of one provider's capabilities for the frontend.

    Stays synchronous and static-only: this reads the table and nothing else,
    so the setup wizard can call it before an org exists. ``models`` is empty
    for ``dynamic_models`` providers — those are filled in separately from the
    org's live host, which needs I/O this function deliberately avoids.
    """
    caps = CAPABILITIES[provider]
    return {
        "provider": provider.value,
        "cli": caps.cli,
        "models": [{"id": m.id, "label": m.label} for m in caps.models],
        "default_model": caps.default_model,
        "supports_effort": caps.supports_effort,
        "effort_values": list(caps.effort_values),
        "supports_iteration_model": caps.supports_iteration_model,
        "auth_modes": [
            {"value": a.value, "label": a.label, "requires_secret": a.requires_secret}
            for a in caps.auth_modes
        ],
        "install_hint": caps.install_hint,
        "docs_url": caps.docs_url,
        # Drives which controls the UI renders, and the callout naming what a
        # provider cannot do — so the UI never offers a setting an adapter
        # would reject, nor a feature the provider cannot run.
        "supports_thinking": caps.supports_thinking,
        "supports_mcp": caps.supports_mcp,
        "supports_files": caps.supports_files,
        "dynamic_models": caps.dynamic_models,
        "requires_base_url": caps.requires_base_url,
        "default_base_url": caps.default_base_url,
        # Named here rather than in the UI's own copy, which drifted stale.
        "limitations": provider_limitations(provider),
    }


async def with_dynamic_models(
    payloads: list[dict[str, Any]], base_url: str | None, api_key: str | None = None
) -> list[dict[str, Any]]:
    """Fill in ``models`` for providers whose models live on the org's host.

    Only tool-capable models are offered: one without that capability answers
    in prose instead of calling a tool, so listing it would let a user pick a
    model that fails at the first agent run.

    ``api_key`` is the org's saved token, for a hosted endpoint behind a
    gateway. Whether it is safe to send depends entirely on where ``base_url``
    came from, which this function cannot see — see :func:`_probe_token`, which
    is the only thing that should be deciding it.

    Never raises. This runs while rendering the settings page, and an
    unreachable host means "nothing to offer" — not a 500 that hides every
    other provider's settings too.
    """
    for payload in payloads:
        if not payload.get("dynamic_models"):
            continue
        target = base_url or payload.get("default_base_url") or OLLAMA_DEFAULT_BASE_URL
        names = await list_tool_models(target, api_key)
        payload["models"] = [{"id": n, "label": n} for n in names]
    return payloads


def _probe_token(org: Organization, requested_base_url: str | None) -> str | None:
    """The token to send while listing models — almost always ``None``.

    Two conditions, and both are load-bearing:

    * **The org must actually be on Ollama.** ``org_api_key`` answers for
      whichever provider it is handed, and every provider names its
      credentialed mode ``api_key`` — so asking it about the org's *current*
      provider returns a Claude / Copilot / Codex secret just as readily. That
      value would then be attached to the request below.
    * **The address must be the org's own saved one.** ``base_url`` is a query
      parameter: the caller chooses the destination. Pairing a stored
      credential with a caller-chosen host is credential exfiltration, however
      the credential itself was obtained — and the settings page re-probes on
      every keystroke, so a saved token would be posted to each half-typed
      prefix of a hostname on the way to the real one.

    The cost is that models do not list until a new hosted address is saved.
    That is the right trade: an unsaved address is exactly the case where we
    cannot know the token belongs to the host being probed.
    """
    if requested_base_url or org.ai_provider != AIProvider.ollama:
        return None
    return org_api_key(capabilities_for(AIProvider.ollama), org)


# Probing a caller-chosen address makes the backend issue a request from inside
# a network the caller's browser cannot reach, so it takes the same permission
# as the settings page that needs it. Reading the table itself does not: Agent
# Prompts renders model dropdowns from it under ``agents:configure``, and a
# route-level dependency would 403 that page instead.
# Called directly rather than declared as a route dependency, so it applies to
# the probe alone. It carries the org_owner bypass with it — re-implementing the
# check inline would drop that and lock owners out of their own settings page.
_require_probe_permission = require_permissions("integrations:configure")


@router.get("/ai/capabilities")
async def get_ai_capabilities(
    base_url: str | None = Query(
        None,
        description="Probe this address instead of the org's saved one, to list "
        "the models of a host being configured but not yet saved.",
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Return all providers' capabilities + the org's current provider + mode."""
    org = await OrganizationRepository(db).get_for_user(current_user)
    if base_url is not None:
        await _require_probe_permission(current_user=current_user, db=db)
    # An unsaved address wins: the Settings page has to show the models of the
    # host being typed, or the user saves a model the new host doesn't have.
    # Validated even though nothing is persisted — the backend still issues the
    # request, from inside a network the caller's browser cannot reach.
    try:
        probe_at = clean_base_url(base_url) or org.ai_base_url
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    providers = await with_dynamic_models(
        [serialize_provider(p) for p in AIProvider], probe_at, _probe_token(org, base_url)
    )
    return {
        "current_provider": (org.ai_provider or AIProvider.claude).value,
        "deployment_mode": deployment_info()["mode"],
        "providers": providers,
    }
