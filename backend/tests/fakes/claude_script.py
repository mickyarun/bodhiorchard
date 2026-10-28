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

"""What a scripted agent run does, and what the fake recorded about it.

A test describes one agent run as an :class:`AgentScript`: the MCP tool
calls the "agent" makes (executed for real against the app's MCP route),
any free text it says along the way, and how the run ends. The class
methods build the failure modes the real CLI produces.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

INSIGHT_BLOCK = (
    "★ Insight ─────────────────────────────────────\n"
    "The learning output style leaked into this run.\n"
    "─────────────────────────────────────────────────\n\n"
)
PREAMBLE = "Sure! I've reviewed the context. Here is the document you asked for:\n\n"


@dataclass(frozen=True)
class ToolCall:
    """One MCP tool call. ``params`` may be computed from the recorded run.

    A callable receives the :class:`AgentRun` so far (prompt, earlier tool
    results), which is how a script echoes ids that only exist at runtime,
    such as the community ids in a synthesis prompt.
    """

    name: str
    params: Mapping[str, Any] | Callable[[AgentRun], Mapping[str, Any]] = field(
        default_factory=dict
    )

    def resolve(self, run: AgentRun) -> dict[str, Any]:
        """The concrete params for this call."""
        raw = self.params(run) if callable(self.params) else self.params
        return dict(raw)


@dataclass(frozen=True)
class Say:
    """Free assistant text emitted mid-run (shows up in stream-json only)."""

    text: str


Step = ToolCall | Say


@dataclass(frozen=True)
class AgentScript:
    """A complete scripted run.

    ``result`` is the final ``result`` text the CLI reports. ``exit_code``,
    ``stderr`` and ``subtype`` shape the failure paths; ``raw_stdout``
    replaces the JSON output entirely (malformed output); ``times_out``
    makes the process never answer so the runner takes its timeout path.
    """

    steps: Sequence[Step] = ()
    result: str = "Done."
    exit_code: int = 0
    stderr: str = ""
    subtype: str = "success"
    raw_stdout: str | None = None
    times_out: bool = False
    cost_usd: float = 0.0123
    num_turns: int = 3

    @classmethod
    def ok(cls, result: str = "Done.", *steps: Step) -> AgentScript:
        """A successful run that makes ``steps`` and reports ``result``."""
        return cls(steps=steps, result=result)

    @classmethod
    def timeout(cls, *steps: Step) -> AgentScript:
        """Makes ``steps`` and then hangs until the runner's deadline."""
        return cls(steps=steps, times_out=True)

    @classmethod
    def crash(cls, exit_code: int = 1, stderr: str = "fatal: agent crashed") -> AgentScript:
        """Exits non-zero with ``stderr`` and no result event."""
        return cls(exit_code=exit_code, stderr=stderr, result="")

    @classmethod
    def malformed(cls, raw: str = "this is not json {") -> AgentScript:
        """Exits 0 but prints ``raw`` instead of the JSON result."""
        return cls(raw_stdout=raw)

    @classmethod
    def max_turns(cls, *steps: Step) -> AgentScript:
        """Runs out of turns: result event with ``error_max_turns``."""
        return cls(steps=steps, subtype="error_max_turns", result="")

    def with_insight(self) -> AgentScript:
        """The same run with a ``★ Insight`` block leaked into the result."""
        return replace(self, result=INSIGHT_BLOCK + self.result)

    def with_preamble(self) -> AgentScript:
        """The same run with chatty framing before the real document."""
        return replace(self, result=PREAMBLE + self.result)


@dataclass
class ToolCallRecord:
    """One tool call as the backend answered it."""

    name: str
    params: dict[str, Any]
    status_code: int | None
    response: Any
    refused: bool = False

    @property
    def is_error(self) -> bool:
        """True when the CLI would surface ``isError`` to the model."""
        if self.refused or self.status_code is None or self.status_code >= 400:
            return True
        return isinstance(self.response, dict) and "error" in self.response


@dataclass
class AgentRun:
    """Everything the fake saw about one spawn of the agent CLI."""

    argv: list[str]
    prompt: str
    cwd: str | None
    env: dict[str, str]
    output_format: str
    mcp_backend_url: str | None = None
    mcp_token: str | None = None
    mcp_tools: list[str] = field(default_factory=list)
    allowed_tools: list[str] = field(default_factory=list)
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    script: AgentScript | None = None
    killed: bool = False

    def flag(self, name: str) -> str | None:
        """Value following ``name`` on the command line, if present."""
        if name in self.argv:
            index = self.argv.index(name)
            if index + 1 < len(self.argv):
                return self.argv[index + 1]
        return None

    def calls_to(self, tool: str) -> list[ToolCallRecord]:
        """Tool calls made to ``tool`` during this run."""
        return [call for call in self.tool_calls if call.name == tool]
