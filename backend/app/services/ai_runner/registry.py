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

"""Resolves the ``AgentProvider`` to use for a given organization.

This is the single switch point for per-org provider selection. Today it
always returns the Claude provider; once the ``ai_provider`` column lands
this branches on ``org.ai_provider`` (claude / copilot / codex).
"""

from app.models.organization import AIProvider, Organization
from app.services.ai_runner.base import AgentProvider
from app.services.ai_runner.claude_provider import ClaudeProvider
from app.services.ai_runner.codex_provider import CodexProvider
from app.services.ai_runner.copilot_provider import CopilotProvider


def provider_instance(provider: AIProvider) -> AgentProvider:
    """Map an :class:`AIProvider` to its adapter (no org needed).

    Used by the pre-init setup connection test, which has no organization yet.
    """
    if provider == AIProvider.copilot:
        return CopilotProvider()
    if provider == AIProvider.codex:
        return CodexProvider()
    return ClaudeProvider()


def provider_for(org: Organization | None = None) -> AgentProvider:
    """Return the agent provider for ``org`` based on ``org.ai_provider``.

    Defaults to Claude when no org is given or the provider is unset.
    """
    provider = org.ai_provider if org is not None else AIProvider.claude
    return provider_instance(provider)
