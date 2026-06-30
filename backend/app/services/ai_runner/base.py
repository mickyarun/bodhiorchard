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

"""Provider abstraction for running agent prompts via a CLI.

Defines the ``AgentProvider`` protocol that every backend agent run goes
through. Concrete providers (Claude / Copilot / Codex) translate the
normalized ``ClaudeRunnerConfig`` into their own CLI invocation and
normalize the output back into a ``ClaudeRunResult``, so the 11+ call
sites and result handlers never change when the org's provider changes.
"""

from pathlib import Path
from typing import Protocol

from app.services.claude_runner import (
    ClaudeRunnerConfig,
    ClaudeRunResult,
    ProgressCallback,
)


class AgentProvider(Protocol):
    """A CLI-backed agent runner.

    The contract mirrors ``run_claude_code``: take a prompt + working dir +
    normalized config, return a normalized ``ClaudeRunResult``. Providers
    that lack a Claude feature (cost telemetry, session resume, ...) degrade
    gracefully by leaving the corresponding result fields ``None``.
    """

    async def run(
        self,
        prompt: str,
        working_dir: str | Path,
        config: ClaudeRunnerConfig | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> ClaudeRunResult:
        """Execute ``prompt`` and return a normalized result."""
        ...
