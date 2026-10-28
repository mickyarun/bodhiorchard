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

"""Record every structlog call made by the modules that handle agent credentials.

``app.main`` configures structlog with ``cache_logger_on_first_use=True``, so
once a module's logger has been used, ``structlog.testing.capture_logs`` no
longer sees it, and whether it was used first depends on test order. The
tap sidesteps that: it replaces the module-level ``logger`` of each listed
module with a recorder for one test, so every event and every keyword those
modules log is captured whatever ran before.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from types import ModuleType
from typing import Any

import pytest

from app.core import encryption
from app.services import (
    agent_activity_logger,
    ai_runner,
    bud_agent_handler,
    claude_env,
    claude_runner,
    job_queue,
)
from app.services.ai_runner import capability_gate

# Every credential variable ``claude_env`` manages, across providers.
CRED_VARS = (
    "ANTHROPIC_API_KEY",
    "CLAUDE_CODE_OAUTH_TOKEN",
    "COPILOT_GITHUB_TOKEN",
    "OPENAI_API_KEY",
    "OLLAMA_API_KEY",
    "GH_TOKEN",
)

# Every module a credential passes through on its way to the agent CLI.
CREDENTIAL_PATH: tuple[ModuleType, ...] = (
    agent_activity_logger,
    ai_runner,
    bud_agent_handler,
    capability_gate,
    claude_env,
    claude_runner,
    encryption,
    job_queue,
)


@dataclass
class LogTap:
    """Captured ``(module, level, event, keywords)`` records."""

    records: list[dict[str, Any]] = field(default_factory=list)

    def install(self, monkeypatch: pytest.MonkeyPatch, *modules: ModuleType) -> None:
        """Replace ``logger`` in ``modules`` (default: the credential path)."""
        for module in modules or CREDENTIAL_PATH:
            monkeypatch.setattr(module, "logger", _Recorder(self, module.__name__))

    def events(self) -> list[str]:
        """Event names in the order they were logged."""
        return [str(record["event"]) for record in self.records]

    def dump(self) -> str:
        """Every record rendered as text, for substring checks."""
        return json.dumps(self.records, default=str)


class _Recorder:
    """Stands in for a bound structlog logger."""

    def __init__(self, tap: LogTap, module: str) -> None:
        self._tap = tap
        self._module = module

    def bind(self, **context: Any) -> _Recorder:
        """Context binding is a no-op for the recorder."""
        return self

    def __getattr__(self, level: str) -> Callable[..., None]:
        def log(event: object = "", *args: object, **keywords: Any) -> None:
            record = {"module": self._module, "level": level, "event": event, "args": args}
            self._tap.records.append({**record, **keywords})

        return log
