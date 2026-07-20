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

"""Which phases a provider can run, stated once for every consumer.

The runtime routing, the API guards and the UI's disabled states all read this.
Three independent answers to the same question is how a phase came to advertise
a button whose only possible outcome was a failed run.
"""

import pytest

from app.models.organization import AIProvider
from app.services.agent_phase_support import (
    PHASES_NAVIGABLE_BY_GRAPH,
    PHASES_REQUIRING_FILES,
    phase_unsupported_reason,
)

_FILE_CAPABLE = [AIProvider.claude, AIProvider.copilot, AIProvider.codex]


@pytest.mark.parametrize("phase", sorted(PHASES_REQUIRING_FILES))
def test_file_less_provider_is_refused_with_an_actionable_reason(phase: str) -> None:
    reason = phase_unsupported_reason(AIProvider.ollama, phase)

    assert reason is not None
    # Must name the blocker and the way out — it replaces a disabled control,
    # so a bare "unsupported" would leave the user with nowhere to go.
    assert "ollama" in reason
    assert "Settings" in reason


@pytest.mark.parametrize("phase", sorted(PHASES_REQUIRING_FILES))
@pytest.mark.parametrize("provider", _FILE_CAPABLE)
def test_cli_providers_run_every_phase(provider: AIProvider, phase: str) -> None:
    """Regression guard: this must not restrict the providers that always worked."""
    assert phase_unsupported_reason(provider, phase) is None


@pytest.mark.parametrize("phase", ["bud", "tech_arch", "closed"])
def test_phases_that_need_no_files_run_anywhere(phase: str) -> None:
    """PRD and learning never took a repo path; tech_arch navigates the call
    graph. None of them depend on a filesystem, so none may be refused."""
    assert phase_unsupported_reason(AIProvider.ollama, phase) is None


def test_the_two_phase_sets_are_disjoint() -> None:
    """A phase cannot both require files and be routed around them."""
    assert not (PHASES_REQUIRING_FILES & PHASES_NAVIGABLE_BY_GRAPH)


def test_unknown_phase_is_not_refused() -> None:
    """An unlisted phase falls through to allowed — run_agent still guards it,
    so a new phase fails loudly there rather than being silently blocked here."""
    assert phase_unsupported_reason(AIProvider.ollama, "some_new_phase") is None
