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

"""Maps a skill's requested model/effort onto a provider's native values.

Split out of ``capabilities.py`` to keep that module focused on the table
itself. Import it from there, not from here, so call sites have one door.
"""

import structlog

from app.models.organization import AIProvider
from app.services.ai_runner.capabilities import CAPABILITIES

logger = structlog.get_logger(__name__)


def resolve_model(
    provider: AIProvider, model: str | None, effort: str | None
) -> tuple[str | None, str | None]:
    """Map a skill's ``model``/``effort`` onto the provider's native values.

    Claude is exact pass-through (today's behaviour). For other providers,
    a model id not in the provider's list falls back to its default, and an
    unsupported effort is dropped — both logged. Empty strings mean "use the
    provider default" and resolve to ``None`` so the adapter omits the flag.
    """
    caps = CAPABILITIES[provider]

    if provider == AIProvider.claude:
        resolved = (model or None, effort or None)
        logger.debug(
            "ai_model_resolved",
            provider="claude",
            requested_model=model or "",
            resolved_model=resolved[0],
            resolved_effort=resolved[1],
        )
        return resolved

    if caps.dynamic_models:
        # The valid set lives on the org's own host, not in the table, so there
        # is nothing to validate against here — pass the id through. Checking
        # it against an empty static tuple would drop every model the user has
        # actually installed. A stale id surfaces as a logged run failure.
        resolved_model: str | None = model or caps.default_model or None
    else:
        valid_ids = {m.id for m in caps.models if m.id}
        if model and model in valid_ids:
            resolved_model = model
        else:
            resolved_model = caps.default_model or None
            if model:
                logger.info(
                    "ai_model_fallback",
                    provider=provider.value,
                    requested=model,
                    used=resolved_model,
                )

    if effort and caps.supports_effort and effort in caps.effort_values:
        resolved_effort: str | None = effort
    else:
        resolved_effort = None
        if effort:
            logger.info("ai_effort_dropped", provider=provider.value, requested=effort)

    logger.debug(
        "ai_model_resolved",
        provider=provider.value,
        requested_model=model or "",
        resolved_model=resolved_model,
        resolved_effort=resolved_effort,
    )
    return (resolved_model, resolved_effort)
