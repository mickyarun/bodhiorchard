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

The tap only covers the listed modules. Tests pair it with pytest's stdlib
capture (``caplog``) and stream capture (``capsys``), which see whatever the
rest of the app logs through structlog's stdlib or print loggers, and assert
the secret is in none of the three. ``claude_provider`` and
``subprocess_env`` sit on the path too but log nothing.
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
    bud_agent_retry,
    claude_env,
    claude_runner,
    job_queue,
    job_utils,
    notification_service,
)
from app.services.ai_runner import capability_gate, cli_exec

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
    bud_agent_retry,
    capability_gate,
    claude_env,
    claude_runner,
    cli_exec,
    encryption,
    job_queue,
    job_utils,
    notification_service,
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


def everything_logged(
    tap: LogTap, caplog: pytest.LogCaptureFixture, capsys: pytest.CaptureFixture[str]
) -> str:
    """The tapped records, the stdlib log records and the captured streams, as one text."""
    streams = capsys.readouterr()
    return "\n".join([tap.dump(), caplog.text, streams.out, streams.err])


def reset_cred_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unset every credential var for one test and forget earlier injections.

    ``setenv`` before ``delenv`` makes teardown restore (or remove) each var
    even when the code under test writes ``os.environ`` directly. The
    ``claude_env`` bookkeeping of what the app injected is emptied too (it
    exists once the host-mode fix lands; ``raising=False`` tolerates its
    absence).
    """
    for var in CRED_VARS:
        monkeypatch.setenv(var, "placeholder")
        monkeypatch.delenv(var)
    for name in ("_app_left", "_host_value"):
        monkeypatch.setattr(claude_env, name, {}, raising=False)
