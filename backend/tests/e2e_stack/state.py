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

"""The fakes installed by :mod:`tests.e2e_stack.serve`, shared with the routes."""

from __future__ import annotations

from dataclasses import dataclass

from tests.fakes.claude_runner import FakeClaudeRunner
from tests.fakes.guard import ExternalCallGuard


@dataclass
class E2EState:
    """Set once at startup; ``None`` only before :func:`serve.install_fakes`."""

    guard: ExternalCallGuard | None = None
    claude: FakeClaudeRunner | None = None


STATE = E2EState()
