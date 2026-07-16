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

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.organization import AIProvider
from app.models.user import User
from app.repositories.organization import OrganizationRepository
from app.services.ai_runner.capabilities import CAPABILITIES
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
    }


@router.get("/ai/capabilities")
async def get_ai_capabilities(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Return all providers' capabilities + the org's current provider + mode."""
    org = await OrganizationRepository(db).get_for_user(current_user)
    return {
        "current_provider": (org.ai_provider or AIProvider.claude).value,
        "deployment_mode": deployment_info()["mode"],
        "providers": [serialize_provider(p) for p in AIProvider],
    }
