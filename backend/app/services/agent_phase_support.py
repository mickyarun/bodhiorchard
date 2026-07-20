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

"""Which BUD phases a provider can actually run.

Each phase gets its repository context differently, and only some of those ways
need a filesystem. Stating that once here keeps the runtime routing, the API
guards and the UI's disabled states from drifting into three different answers
to the same question — the drift that let a phase advertise a button whose only
possible outcome was a failed run.

The split is decided by what the phase's prompt tells the agent to do, not by
whether a ``working_dir`` happens to be passed:

* **Requires files** — the prompt hands over ``git fetch`` / ``git diff``
  commands to run. A diff has no equivalent in the cached call graph, so a
  provider with no shell cannot substitute anything for it.
* **Graph-navigable** — the prompt directs the agent to the code-intel MCP
  tools, which serve the call graph out of Postgres. The ``working_dir`` is
  only a convenience for a CLI that may also ``Read``.
* **Neither** — the phase never took a repo path (PRD, learning): its context
  is already in the prompt.

The diff *could* be served as an MCP tool the backend fills from local git,
which would move the first group into the second. Until then, refusing is the
honest answer: routing those phases around the filesystem would buy a confident
review of code the agent never saw.
"""

from __future__ import annotations

from app.models.organization import AIProvider
from app.services.ai_runner.capabilities import capabilities_for

__all__ = [
    "PHASES_NAVIGABLE_BY_GRAPH",
    "PHASES_REQUIRING_FILES",
    "phase_unsupported_reason",
]

# Prompts issue git commands; nothing else can stand in for the diff.
PHASES_REQUIRING_FILES = frozenset({"code_review", "testing"})

# Explores through the code-intel MCP tools, so the repo path is optional.
PHASES_NAVIGABLE_BY_GRAPH = frozenset({"tech_arch"})

_PHASE_LABELS = {
    "code_review": "Code review",
    "testing": "Test generation",
}


def phase_unsupported_reason(provider: AIProvider, phase: str) -> str | None:
    """Explain why ``provider`` cannot run ``phase``, or ``None`` if it can.

    The string is user-facing: it names the blocker and the way out, because it
    is shown in place of a disabled control rather than after a failed run.
    """
    if phase not in PHASES_REQUIRING_FILES:
        return None
    caps = capabilities_for(provider)
    if caps.supports_files:
        return None
    label = _PHASE_LABELS.get(phase, phase)
    return (
        f"{label} reads the branch diff from the repository, which the "
        f"{provider.value} provider cannot do — it runs over HTTP with no "
        "filesystem or git access. Switch to a CLI-based provider in "
        "Settings → AI Config to use this phase."
    )
