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

"""Security guardrails for the ``claude`` subprocess.

Every spawn of the Claude CLI from this codebase runs with
``--dangerously-skip-permissions`` (YOLO mode), which trusts the model with
unrestricted tool use. Prompt-injection content in a scanned repo (README,
commit messages, BUD doc bodies) can therefore push the subprocess into:

* exfiltrating ``ANTHROPIC_API_KEY`` / ``ENCRYPTION_KEY`` / GitHub PATs via
  ``curl`` or DNS,
* reading ``.env`` / ``~/.ssh`` / ``~/.aws``,
* dropping database tables via ``psql``,
* force-pushing or wiping branches,
* persisting via a planted ``.claude/settings.json`` hook.

This package implements the layered defense documented in the project plan
``plans/claude-we-are-running-parallel-hickey.md``:

* ``env_filter`` — Layer 4. Whitelist the env vars the subprocess inherits.
* ``resource_limits`` — Audit/limits. Kernel-enforced memory + process caps.
* (later) ``deny_rules`` / ``inline_settings`` / ``pretool_guard`` — Layers
  2–3. Inline ``permissions.deny`` JSON and a PreToolUse hook script.
"""

from app.services.claude_guard.env_filter import build_claude_env
from app.services.claude_guard.resource_limits import apply_subprocess_rlimits

__all__ = ["apply_subprocess_rlimits", "build_claude_env"]
