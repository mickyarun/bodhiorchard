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

"""Shape of a provider capability descriptor.

Split from ``capabilities.py`` so that module holds only the table itself.
Import these from ``capabilities``, which re-exports them — this module has no
dependencies of its own beyond the provider enum, which keeps it importable
from anywhere without cycles.
"""

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass

from app.models.organization import AIProvider


@dataclass(frozen=True)
class ModelChoice:
    """A selectable model for a provider (UI label + native id)."""

    id: str
    label: str


@dataclass(frozen=True)
class AuthModeSpec:
    """An auth mode a provider supports and the env var(s) it sets.

    ``requires_secret`` modes store an encrypted credential on the org;
    ``host`` modes inherit credentials from the process / CLI login. A
    provider needing no credential at all (Ollama) still declares a ``host``
    mode, so the UI always has something to render.
    """

    value: str
    label: str
    requires_secret: bool
    env_vars: tuple[str, ...]


@dataclass(frozen=True)
class ProviderCapabilities:
    """Everything the UI and backend need to drive one provider.

    ``cli``/``version_cmd`` are optional because not every provider is a CLI:
    Ollama is an HTTP server, so it is probed via ``preflight`` instead.
    """

    provider: AIProvider
    cli: str | None
    models: tuple[ModelChoice, ...]
    default_model: str
    supports_effort: bool
    effort_values: tuple[str, ...]
    supports_iteration_model: bool
    auth_modes: tuple[AuthModeSpec, ...]
    version_cmd: tuple[str, ...] | None
    install_hint: str
    docs_url: str
    # What the provider can actually DO. Without these, a feature needing
    # tools or file access silently returns plausible emptiness on a provider
    # that cannot do it; ``run_agent`` gates on them instead.
    supports_mcp: bool = True
    supports_files: bool = True
    supports_resume: bool = True
    # Reasoning as a boolean (Ollama's `think`) rather than a level. Providers
    # with graded reasoning use ``supports_effort``/``effort_values``.
    supports_thinking: bool = False
    # Models come from the org's own host, not this table.
    dynamic_models: bool = False
    requires_base_url: bool = False
    default_base_url: str | None = None
    # Local inference is far slower than a hosted API, and an unbounded tool
    # loop on a small model is a real hazard. Applied at the seam so call
    # sites keep their own numbers.
    timeout_multiplier: float = 1.0
    max_turns_cap: int | None = None
    # Liveness probe for providers with no CLI to version-check.
    preflight: Callable[[Mapping[str, str] | None], Awaitable[str | None]] | None = None
